const fs = require('fs');
const path = require('path');
const Database = require('better-sqlite3');

const MATERIAL_DIR = path.resolve(__dirname, '../资料');
const DB_PATH = path.resolve(__dirname, '../.metadata/knowledge-base.db');
const INDEX_MD = path.resolve(__dirname, '../INDEX.md');

// Ollama API 配置
const OLLAMA_API = 'http://localhost:11434/api/generate';
const MODEL = 'qwen2.5';

const SUPPORTED_EXT = new Set(['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.txt', '.md']);

/**
 * Ollama 本地模型翻译
 */
async function ollamaTranslate(query, from = 'zh', to = 'en') {
  const prompt = `将以下${from === 'zh' ? '中文' : '英文'}文本翻译成${to === 'en' ? '英文' : '中文'}，只返回翻译结果，不要任何解释：${query}`;

  try {
    const response = await fetch(OLLAMA_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: MODEL,
        prompt: prompt,
        stream: false,
      }),
    });

    if (!response.ok) {
      throw new Error(`Ollama 响应错误：${response.status}`);
    }

    const result = await response.json();
    return result.response.trim();
  } catch (e) {
    throw new Error(`Ollama 调用失败：${e.message}`);
  }
}

/**
 * 将文件名转换为英文
 */
async function translateFilename(chineseName) {
  const extMatch = chineseName.match(/^(.+)\.([^.]+)$/);
  if (!extMatch) return chineseName;

  const name = extMatch[1];
  const ext = extMatch[2];

  try {
    const translated = await ollamaTranslate(name);
    const safeName = translated
      .replace(/[^a-zA-Z0-9\s_-]/g, '')
      .replace(/\s+/g, '-')
      .toLowerCase();
    return `${safeName}.${ext}`;
  } catch (e) {
    console.error(`翻译失败：${e.message}`);
    return null;
  }
}

/**
 * 扫描目录获取文件列表
 */
function scanDir(dir) {
  const files = [];
  const EXCLUDED_DIRS = new Set(['node_modules', '.scripts', '.git', 'dist', '.vscode']);
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (EXCLUDED_DIRS.has(entry.name)) continue;
      files.push(...scanDir(full));
    }
    else if (entry.isFile() && SUPPORTED_EXT.has(path.extname(entry.name).toLowerCase())) files.push(full);
  }
  return files;
}

async function main() {
  // 步骤 1: 重命名中文文件
  console.log('[步骤 1] 检查中文文件名...');
  const allFilesStep1 = scanDir(MATERIAL_DIR);
  const chineseFiles = allFilesStep1.filter(f => /[\u4e00-\u9fa5]/.test(path.basename(f)));
  console.log(`发现 ${chineseFiles.length} 个中文文件名`);

  for (const file of chineseFiles) {
    const dir = path.dirname(file);
    const base = path.basename(file);
    const newName = await translateFilename(base);

    if (newName && newName !== base) {
      const newPath = path.join(dir, newName);

      if (fs.existsSync(newPath)) {
        console.log(`  跳过：${base} -> ${newName} (目标已存在)`);
      } else {
        fs.renameSync(file, newPath);
        console.log(`  重命名：${base} -> ${newName}`);
      }
    }
  }

  // 步骤 2: 重新扫描文件
  console.log('\n[步骤 2] 扫描文件...');
  const allFiles = scanDir(MATERIAL_DIR);
  console.log(`找到 ${allFiles.length} 个文件`);

  // 从 SQLite 数据库读取已索引的文件路径
  let indexedPaths = new Set();
  let indexedData = {};
  if (fs.existsSync(DB_PATH)) {
    try {
      const db = new Database(DB_PATH);
      const rows = db.prepare("SELECT * FROM files WHERE status = 'indexed'").all();
      for (const r of rows) {
        indexedPaths.add(r.path);
        indexedData[r.fingerprint] = {
          fingerprint: r.fingerprint,
          path: r.path,
          size: r.size,
          mtime: r.mtime,
          status: r.status,
          indexedAt: r.indexed_at,
          chunksCount: r.chunks_count,
        };
      }
      db.close();
    } catch (e) {
      console.error('读取数据库失败:', e.message);
    }
  }

  // 同步更新 file-index.json（兼容性备份）
  const INDEX_JSON = path.resolve(__dirname, '../.metadata/file-index.json');
  fs.writeFileSync(INDEX_JSON, JSON.stringify(indexedData, null, 2), 'utf-8');

  const pending = allFiles.filter(f => !indexedPaths.has(f));

  const lines = [
    '# 待索引资料清单',
    '',
    `更新时间：${new Date().toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}`,
    `共 ${pending.length} 个文件待索引`,
    '',
  ];

  if (pending.length === 0) {
    lines.push('所有文件已索引完毕。');
  } else {
    lines.push('| 文件名 | 路径 |');
    lines.push('|--------|------|');
    for (const f of pending) {
      lines.push(`| ${path.basename(f)} | ${f} |`);
    }
  }

  fs.writeFileSync(INDEX_MD, lines.join('\n') + '\n', 'utf-8');
  console.log(`INDEX.md 已更新，${pending.length} 个文件待索引`);
}

main().catch(console.error);

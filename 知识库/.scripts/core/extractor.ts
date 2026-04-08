import * as fs from "fs";
import * as path from "path";
import { spawnSync } from "child_process";
import { FingerprintManager, FileFingerprint } from "./fingerprint";
import { Chunker } from "./chunker";
import { KeywordIndexer } from "./keyword-index";
import { VectorIndexer } from "./vector-index";
import { ContentStore } from "./content-store";
import { kbLogger } from "./logger";
import * as tmp from "tmp";

// 加载配置文件
const CONFIG_PATH = path.resolve(__dirname, "../../config.json");
let config: any = {};
try {
  config = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8"));
} catch (e) {
  kbLogger.warn("无法加载配置文件，使用默认配置");
}

const MATERIAL_DIR = path.resolve(__dirname, "../../../资料");
const SUPPORTED_EXT = new Set([".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".txt", ".md", ".jpg", ".jpeg", ".png", ".bmp"]);
const EXCLUDED_DIRS = new Set(["node_modules", ".scripts", ".git", "dist", ".vscode"]);

// OCR 降级方案 1：PaddleOCR（本地 Python 脚本）
async function fallbackToPaddleOcr(filePath: string): Promise<string> {
  const ocrConfig = config.ocr || {};
  if (!ocrConfig.enabled) return "";

  const pythonScript = ocrConfig.pythonScript || path.join(__dirname, "ocr-helper.py");

  if (!fs.existsSync(pythonScript)) {
    kbLogger.error(`OCR 脚本不存在：${pythonScript}`);
    return "";
  }

  try {
    let pythonCmd = ocrConfig.pythonPath === "auto" ? "python" : ocrConfig.pythonPath;

    const pythonRoot = ocrConfig.pythonPath === "auto" ? './.models/python11' : path.dirname(path.dirname(ocrConfig.pythonPath));
    const cudnnBinPath = path.join(pythonRoot, 'Lib/site-packages/nvidia/cudnn/bin').replace(/\//g, '\\');
    const cublasBinPath = path.join(pythonRoot, 'Lib/site-packages/nvidia/cublas/bin').replace(/\//g, '\\');
    const nvrtcBinPath = path.join(pythonRoot, 'Lib/site-packages/nvidia/cuda_nvrtc/bin').replace(/\//g, '\\');
    const systemPaths = ['C:\\Windows\\system32', 'C:\\Windows\\sysnative'];
    const newPath = [cudnnBinPath, cublasBinPath, nvrtcBinPath, ...systemPaths].join(';') + (process.env.PATH ? `;${process.env.PATH}` : '');

    const b64path = Buffer.from(filePath, 'utf-8').toString('base64');
    const result = spawnSync(pythonCmd, [pythonScript, `--b64path=${b64path}`, "true"], {
      encoding: "utf-8",
      timeout: 300000,
      maxBuffer: 50 * 1024 * 1024,
      env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', PATH: newPath, 'FLAGS_cudnn_deterministic': 'false', 'FLAGS_cudnn_batchnorm_spatial_persistent': 'false' }
    });

    if (result.status === 0) {
      const output = JSON.parse(result.stdout);
      if (output.success) {
        kbLogger.info(`PaddleOCR 识别成功，置信度：${(output.confidence * 100).toFixed(1)}%`);
        return output.text;
      } else {
        kbLogger.warn(`PaddleOCR 失败：${output.error}`);
      }
    } else {
      kbLogger.warn(`Python 脚本执行失败：${result.stderr}`);
    }
  } catch (e: any) {
    kbLogger.warn(`PaddleOCR 异常：${e.message}`);
  }

  return "";
}

// OCR 特定页面（用于混合模式）
async function ocrPdfPages(filePath: string, pages: number[]): Promise<Map<number, string>> {
  const ocrConfig = config.ocr || {};
  const pythonScript = ocrConfig.pythonScript || path.join(__dirname, "ocr-helper.py");
  const pythonCmd = ocrConfig.pythonPath === "auto" ? "python" : ocrConfig.pythonPath;

  if (!fs.existsSync(pythonScript)) {
    kbLogger.error(`OCR 脚本不存在：${pythonScript}`);
    return new Map();
  }

  try {
    const pythonRoot = ocrConfig.pythonPath === "auto" ? './.models/python11' : path.dirname(path.dirname(ocrConfig.pythonPath));
    const cudnnBinPath = path.join(pythonRoot, 'Lib/site-packages/nvidia/cudnn/bin').replace(/\//g, '\\');
    const cublasBinPath = path.join(pythonRoot, 'Lib/site-packages/nvidia/cublas/bin').replace(/\//g, '\\');
    const nvrtcBinPath = path.join(pythonRoot, 'Lib/site-packages/nvidia/cuda_nvrtc/bin').replace(/\//g, '\\');
    const systemPaths = ['C:\\Windows\\system32', 'C:\\Windows\\sysnative'];
    const newPath = [cudnnBinPath, cublasBinPath, nvrtcBinPath, ...systemPaths].join(';') + (process.env.PATH ? `;${process.env.PATH}` : '');

    const b64path = Buffer.from(filePath, 'utf-8').toString('base64');
    const pagesStr = pages.join(',');
    const result = spawnSync(pythonCmd, [pythonScript, `--b64path=${b64path}`, `--pages=${pagesStr}`], {
      encoding: "utf-8",
      timeout: 900000,
      maxBuffer: 500 * 1024 * 1024,
      env: { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', PATH: newPath }
    });

    kbLogger.info(`[ocrPdfPages] OCR 结果：status=${result?.status}`);

    if (result.status === 0) {
      const output = JSON.parse(result.stdout);
      if (output.success && output.page_results) {
        const pageResults = new Map<number, string>();
        for (const [pageNum, text] of Object.entries(output.page_results)) {
          pageResults.set(parseInt(pageNum), text as string);
        }
        kbLogger.info(`页面 OCR 成功，处理了 ${pageResults.size} 页`);
        return pageResults;
      }
    }
  } catch (e: any) {
    kbLogger.error(`页面 OCR 异常：${e.message}`);
  }

  return new Map();
}

// 对 PDF 进行 OCR（整个文件，向后兼容）
async function ocrPdfFile(filePath: string): Promise<string> {
  kbLogger.info(`[ocrPdfFile] 开始处理：${filePath}`);
  const pythonScript = config.ocr?.pythonScript || path.join(__dirname, "ocr-helper.py");
  const pythonCmd = config.ocr?.pythonPath === "auto" ? "python" : config.ocr?.pythonPath;
  const pythonRoot = config.ocr?.pythonPath === "auto" ? './.models/python11' : path.dirname(path.dirname(config.ocr?.pythonPath || ''));
  const cudnnBinPath = path.join(pythonRoot, 'Lib/site-packages/nvidia/cudnn/bin').replace(/\//g, '\\');
  const cublasBinPath = path.join(pythonRoot, 'Lib/site-packages/nvidia/cublas/bin').replace(/\//g, '\\');
  const nvrtcBinPath = path.join(pythonRoot, 'Lib/site-packages/nvidia/cuda_nvrtc/bin').replace(/\//g, '\\');
  const systemPaths = ['C:\\Windows\\system32', 'C:\\Windows\\sysnative'];
  const newPath = [cudnnBinPath, cublasBinPath, nvrtcBinPath, ...systemPaths].join(';') + (process.env.PATH ? `;${process.env.PATH}` : '');

  const env = { ...process.env, PYTHONUTF8: '1', PYTHONIOENCODING: 'utf-8', PATH: newPath };

  let targetPath = filePath;
  let tempFile = '';
  const hasChinese = /[\u4e00-\u9fa5]/.test(filePath);
  kbLogger.info(`[ocrPdfFile] 路径是否有中文：${hasChinese}`);

  if (hasChinese) {
    try {
      const tmpDir = path.join(__dirname, '../../.tmp/ocr');
      if (!fs.existsSync(tmpDir)) {
        fs.mkdirSync(tmpDir, { recursive: true });
      }
      tempFile = path.join(tmpDir, `pdf_${Date.now()}.pdf`);
      fs.copyFileSync(filePath, tempFile);
      targetPath = tempFile;
      kbLogger.info(`临时文件：${targetPath}`);
    } catch (e: any) {
      kbLogger.error(`复制临时文件失败：${e.message}`);
      return "";
    }
  }

  kbLogger.info(`[ocrPdfFile] 调用 OCR 脚本：${targetPath}`);
  try {
    const b64path = Buffer.from(targetPath, 'utf-8').toString('base64');
    const result = spawnSync(pythonCmd, [pythonScript, `--b64path=${b64path}`, "true"], {
      encoding: "utf-8",
      timeout: 900000,
      maxBuffer: 500 * 1024 * 1024,
      env
    });

    kbLogger.info(`[ocrPdfFile] OCR 结果：status=${result?.status}, stdout=${result?.stdout?.substring(0, 200)}, stderr=${result?.stderr?.substring(0, 200)}`);

    if (result.status === 0) {
      const output = JSON.parse(result.stdout);
      if (output.success) {
        kbLogger.info(`PDF OCR 识别成功，置信度：${(output.confidence * 100).toFixed(1)}%`);
        return output.text;
      } else {
        kbLogger.warn(`PDF OCR 失败：${output.error}`);
      }
    } else {
      kbLogger.warn(`Python 脚本执行失败：${result.stderr}`);
    }
  } catch (e: any) {
    kbLogger.error(`OCR PDF 异常：${e.message}`);
  } finally {
    if (tempFile && fs.existsSync(tempFile)) {
      try { fs.unlinkSync(tempFile); } catch {}
    }
  }

  return "";
}

// OCR 降级方案 2：parseflow MCP（备用）
async function fallbackToParseflow(filePath: string): Promise<string> {
  try {
    const parseflowPath = config.parseflowMcpPath || "D:/claude code/parseflow-mcp/packages/mcp-server/dist/index.js";
    const result = spawnSync("node", [
      "-e",
      `const { StdioClientTransport } = require("@modelcontextprotocol/sdk/client/stdio"); const { Client } = require("@modelcontextprotocol/sdk/client/index"); const t = new StdioClientTransport({ command: "node", args: ["${parseflowPath}"] }); const c = new Client({ name: "kb", version: "1.0" }, { capabilities: {} }); (async () => { await c.connect(t); const r = await c.callTool({ name: "extract_ocr", arguments: { filePath: "${filePath}" } }); kbLogger.info(JSON.stringify(r.content[0].text)); process.exit(0); })();`
    ], { encoding: "utf-8", timeout: 120000 });
    const output = result.stdout?.trim();
    if (output) {
      try {
        const parsed = JSON.parse(output);
        return typeof parsed === "string" ? parsed : "";
      } catch {
        return "";
      }
    }
    return "";
  } catch {
    return "";
  }
}

// 统一的 OCR 降级入口
async function fallbackToOcr(filePath: string): Promise<string> {
  kbLogger.info(`开始 OCR 识别：${filePath}`);

  let text = await fallbackToPaddleOcr(filePath);

  if (text.length < 10) {
    kbLogger.info(`PaddleOCR 结果过短，尝试 parseflow MCP`);
    text = await fallbackToParseflow(filePath);
  }

  return text;
}

async function extractText(filePath: string): Promise<string> {
  const ext = path.extname(filePath).toLowerCase();

  if (ext === ".txt" || ext === ".md") {
    return fs.readFileSync(filePath, "utf-8");
  }

  // 图片文件直接 OCR
  if ([".jpg", ".jpeg", ".png", ".bmp"].includes(ext)) {
    kbLogger.info (`图片文件，直接 OCR: ${filePath}`);
    return await fallbackToOcr(filePath);
  }

  let text = "";

  if (ext === ".pdf") {
    try {
      kbLogger.info(`[PDF 处理] 开始处理：${filePath}`);
      const { getDocument } = await import("pdfjs-dist/legacy/build/pdf.mjs" as any);
      const cMapUrl = path.resolve(__dirname, "../../../.scripts/node_modules/pdfjs-dist/cmaps/") + "/";
      const data = new Uint8Array(fs.readFileSync(filePath));
      const doc = await getDocument({ data, cMapUrl, cMapPacked: true }).promise;
      kbLogger.info(`[PDF 处理] 页面数：${doc.numPages}`);

      const pdfTextPages: string[] = [];
      const pagesNeedOcr: number[] = [];

      // 逐页检测：有文本层的页面直接提取，没有文本层的页面标记为 OCR
      for (let i = 1; i <= doc.numPages; i++) {
        const page = await doc.getPage(i);
        const content = await page.getTextContent();
        const pageText = content.items.map((item: any) => item.str).join(" ");

        if (pageText.trim().length > 50) {
          // 这页有足够多的文本层，直接提取
          pdfTextPages.push(pageText);
        } else {
          // 这页文本太少或没有，需要 OCR（可能是扫描版或图片页）
          pagesNeedOcr.push(i);
          pdfTextPages.push(""); // 占位
        }
      }

      kbLogger.info(`[PDF 处理] 需要 OCR 的页面数：${pagesNeedOcr.length}`);

      // 逐页混合处理
      if (pagesNeedOcr.length > 0) {
        kbLogger.info(`PDF 中有 ${pagesNeedOcr.length}/${doc.numPages} 页需要 OCR，逐页混合处理`);

        // 只 OCR 需要 OCR 的页面
        const ocrResults = await ocrPdfPages(filePath, pagesNeedOcr);

        // 合并文本提取和 OCR 结果
        const finalTexts: string[] = [];
        let ocrPageIndex = 0;

        for (let i = 0; i < doc.numPages; i++) {
          const pageNum = i + 1;
          if (pagesNeedOcr.includes(pageNum)) {
            // 这页是 OCR 的
            const ocrText = ocrResults.get(pageNum) || "";
            finalTexts.push(ocrText);
            if (ocrText) {
              kbLogger.info(`第 ${pageNum} 页 OCR 文本长度：${ocrText.length}`);
            }
          } else {
            // 这页是文本提取的
            finalTexts.push(pdfTextPages[i] || "");
          }
        }

        text = finalTexts.filter(t => t.trim()).join("\n");
        kbLogger.info(`[混合处理] 最终文本长度：${text.length}`);
      } else {
        // 没有扫描版页面，使用提取的文本
        text = pdfTextPages.filter(t => t.trim()).join("\n");
        kbLogger.info(`[PDF 处理] 提取文本长度：${text.length}`);
      }
    } catch (e: any) {
      kbLogger.error(`PDF 解析失败：${e.message}`);
    }

  } else if (ext === ".docx" || ext === ".pptx" || ext === ".ppt" || ext === ".xlsx" || ext === ".xls" || ext === ".odt" || ext === ".odp" || ext === ".ods") {
    try {
      const { parseOffice } = require("officeparser");
      const ast = await parseOffice(filePath);
      function extractFromAst(node: any): string {
        if (!node) return "";
        if (typeof node === "string") return node;
        if (node.text) return node.text;
        if (Array.isArray(node)) return node.map(extractFromAst).join(" ");
        if (node.children) return extractFromAst(node.children);
        if (node.content) return extractFromAst(node.content);
        return "";
      }
      text = extractFromAst(ast);
    } catch (e: any) { kbLogger.error(`Office 解析失败：${e.message}`); }

  } else if (ext === ".doc") {
    text = await fallbackToOcr(filePath);
  }

  return text;
}

function scanDir(dirPath: string, recursive: boolean): string[] {
  const files: string[] = [];
  for (const entry of fs.readdirSync(dirPath, { withFileTypes: true })) {
    const full = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      if (EXCLUDED_DIRS.has(entry.name)) continue;
      if (recursive) files.push(...scanDir(full, true));
    } else if (entry.isFile() && SUPPORTED_EXT.has(path.extname(entry.name).toLowerCase())) {
      files.push(full);
    }
  }
  return files;
}

export class ReExtractor {
  constructor(
    private fm: FingerprintManager,
    private chunker: Chunker,
    private kwIndexer: KeywordIndexer,
    private vecIndexer: VectorIndexer,
    private store: ContentStore
  ) {}

  async init(): Promise<void> {
    await this.vecIndexer.init();
  }

  async extractFile(filePath: string): Promise<{
    success: boolean;
    fingerprint?: string;
    chunksCount?: number;
    error?: string;
  }> {
    filePath = path.resolve(filePath);
    if (!fs.existsSync(filePath)) {
      return { success: false, error: `文件不存在：${filePath}` };
    }

    const fingerprint = this.fm.compute(filePath);

    if (this.fm.isIndexed(fingerprint) && !this.fm.isModified(filePath)) {
      return { success: true, fingerprint, chunksCount: 0 };
    }

    const stat = fs.statSync(filePath);
    this.fm.record({
      fingerprint,
      path: filePath,
      size: stat.size,
      mtime: stat.mtime.toISOString(),
      status: "indexing",
    });

    let text: string;
    try {
      text = await extractText(filePath);
    } catch (e: any) {
      this.fm.record({ fingerprint, path: filePath, size: stat.size, mtime: stat.mtime.toISOString(), status: "error" });
      return { success: false, fingerprint, error: `提取文本失败：${e.message}` };
    }

    let chunks;
    try {
      chunks = this.chunker.split(text, fingerprint);
    } catch (e: any) {
      this.fm.record({ fingerprint, path: filePath, size: stat.size, mtime: stat.mtime.toISOString(), status: "error" });
      return { success: false, fingerprint, error: `分块失败：${e.message}` };
    }

    for (const chunk of chunks) {
      try {
        chunk.vector = await this.vecIndexer.embed(chunk.text);
        this.vecIndexer.add(chunk.id, chunk.vector);
      } catch {
        // 向量失败不阻塞
      }
    }

    this.kwIndexer.addBatch(chunks);
    this.vecIndexer.save(fingerprint);
    this.store.save(fingerprint, chunks);

    const info: FileFingerprint = {
      fingerprint,
      path: filePath,
      size: stat.size,
      mtime: stat.mtime.toISOString(),
      status: "indexed",
      indexedAt: new Date().toISOString(),
      chunksCount: chunks.length,
    };
    this.fm.record(info);

    return { success: true, fingerprint, chunksCount: chunks.length };
  }

  async extractDirectory(dirPath: string, recursive = true): Promise<{
    total: number; success: number; failed: number; errors: string[];
  }> {
    dirPath = path.resolve(dirPath);
    const files = scanDir(dirPath, recursive);
    let success = 0, failed = 0;
    const errors: string[] = [];

    const indexerConfig = config.indexer || {};
    const concurrency = indexerConfig.concurrency || 5;

    kbLogger.info(`[索引] 开始索引目录：${dirPath}，共 ${files.length} 个文件，并发数：${concurrency}`);

    const processFile = async (f: string) => {
      const result = await this.extractFile(f);
      if (result.success) {
        success++;
      } else {
        failed++;
        if (result.error) errors.push(result.error);
      }
    };

    const chunks: string[][] = [];
    for (let i = 0; i < files.length; i += concurrency) {
      chunks.push(files.slice(i, i + concurrency));
    }

    for (const chunk of chunks) {
      await Promise.all(chunk.map(processFile));
    }

    kbLogger.info(`[索引] 完成：成功 ${success} 个，失败 ${failed} 个`);
    return { total: files.length, success, failed, errors };
  }

  async incrementalUpdate(): Promise<{
    scanned: number; newFiles: number; modifiedFiles: number; removedFiles: number; processed: number;
  }> {
    const files = scanDir(MATERIAL_DIR, true);
    let newFiles = 0, modifiedFiles = 0, processed = 0;

    const indexerConfig = config.indexer || {};
    const concurrency = indexerConfig.concurrency || 5;

    kbLogger.info(`[索引] 增量更新：扫描 ${files.length} 个文件，并发数：${concurrency}`);

    const filesToProcess: string[] = [];
    for (const f of files) {
      const fp = this.fm.compute(f);
      if (!this.fm.isIndexed(fp)) {
        newFiles++;
        filesToProcess.push(f);
      } else if (this.fm.isModified(f)) {
        modifiedFiles++;
        filesToProcess.push(f);
      }
    }

    kbLogger.info(`[索引] 新文件：${newFiles}，修改文件：${modifiedFiles}`);

    const processFile = async (f: string) => {
      const result = await this.extractFile(f);
      if (result.success) processed++;
    };

    const chunks: string[][] = [];
    for (let i = 0; i < filesToProcess.length; i += concurrency) {
      chunks.push(filesToProcess.slice(i, i + concurrency));
    }

    for (const chunk of chunks) {
      await Promise.all(chunk.map(processFile));
    }

    const indexed = this.fm.getIndexedFiles();
    let removedFiles = 0;
    for (const entry of indexed) {
      if (!fs.existsSync(entry.path)) {
        this.store.remove(entry.fingerprint);
        this.vecIndexer.remove(entry.fingerprint);
        removedFiles++;
      }
    }

    kbLogger.info(`[索引] 增量更新完成：处理 ${processed} 个，删除 ${removedFiles} 个`);
    return { scanned: files.length, newFiles, modifiedFiles, removedFiles, processed };
  }

  async reindex(fingerprint: string): Promise<void> {
    const indexed = this.fm.getIndexedFiles();
    const entry = indexed.find(e => e.fingerprint === fingerprint);
    if (!entry) throw new Error(`找不到指纹：${fingerprint}`);
    this.store.remove(fingerprint);
    this.vecIndexer.remove(fingerprint);
    await this.extractFile(entry.path);
  }
}

# 备份目录

本目录用于存放修改前的原始文件备份。

## 备份文件列表

| 备份文件 | 原始文件 | 备份时间 | 说明 |
|---------|---------|---------|------|
| `keyword-index.ts.bak` | `core/keyword-index.ts` | 2026-02-25 | 原始 N-gram 分词 |
| `chunker.ts.bak` | `core/chunker.ts` | 2026-02-25 | 原始固定字符数分块 |
| `chunker.ts.bak.v2` | `core/chunker.ts` | 2026-02-25 | 语义自适应分块（改进后） |
| `config.json.bak` | `config.json` | 2026-02-25 | 原始配置文件 |
| `ocr-helper.py.bak` | `core/ocr-helper.py` | 2026-02-25 | 原始 OCR 脚本 |

## 恢复方法

如需恢复原始文件，执行：

```bash
# 恢复 keyword-index.ts（原始 N-gram 分词）
cp G:/知识库/.scripts/backup/keyword-index.ts.bak G:/知识库/.scripts/core/keyword-index.ts

# 恢复 chunker.ts（原始固定字符数分块）
cp G:/知识库/.scripts/backup/chunker.ts.bak G:/知识库/.scripts/core/chunker.ts

# 恢复 config.json
cp G:/知识库/.scripts/backup/config.json.bak G:/知识库/.scripts/config.json

# 恢复 ocr-helper.py
cp G:/知识库/.scripts/backup/ocr-helper.py.bak G:/知识库/.scripts/core/ocr-helper.py
```

## 修改内容摘要

### keyword-index.ts 改进
- 集成 jieba 中文分词
- 自动检测 jieba 可用性，失败时回退到 N-gram
- 支持自定义专业词典

### chunker.ts 改进
- 不再使用固定 1000 字符切分
- 按自然段落（空行）分块
- 列表项尽量保持完整
- 过长段落在句子边界切断
- 调整默认参数：chunkSize 800, maxChunkSize 1500, overlap 100

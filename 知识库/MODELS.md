# 模型配置说明

本项目使用以下本地模型，需要手动下载。所有模型文件约 **200MB**。

## 1. Qwen2.5 (Ollama) — 知识库摘要

用于知识库检索后本地 AI 总结，节省 API Token。

**版本要求**: Qwen2.5 7B 或更高（qwen2.5:7b）

**安装 Ollama**:
- macOS/Linux: `curl -fsSL https://ollama.ai/install.sh | sh`
- Windows: 从 https://ollama.ai 下载安装包

**下载模型**:
```bash
ollama pull qwen2.5:7b
```

**验证安装**: `ollama list` 应显示 qwen2.5:7b

## 2. BGE-small-zh-v1.5 — 向量嵌入

用于中文语义向量化，支持本地离线运行。

**下载地址**（二选一）:

| 源 | 链接 |
|---|------|
| Hugging Face | https://huggingface.co/BAAI/bge-small-zh-v1.5 |
| ModelScope | https://modelscope.cn/models/Xorbits/bge-small-zh-v1.5 |

**版本**: 1.5 固定版本，无需选择

**安放路径**: `知识库/.models/bge-small-zh-v1.5/`

**目录结构**:
```
知识库/.models/bge-small-zh-v1.5/
├── config.json
├── model.onnx          # 向量模型（核心）
├── tokenizer.json
├── tokenizer_config.json
└── vocab.txt
```

## 3. PaddleOCR — 文本识别（可选）

用于 PDF、图片内的文字识别。

**下载地址**: https://github.com/PaddlePaddle/PaddleOCR/releases

**推荐版本**: PaddleOCR 2.7+

**安放路径**: `知识库/.models/paddleocr-models/whl/`

**需要模型**:
- `ch_PP-OCRv4_det_infer` — 文本检测
- `ch_PP-OCRv4_rec_infer` — 文本识别
- `ch_ppocr_mobile_v2.0_cls_infer` — 方向分类

**不安装此模型的影响**: PDF/图片类资料无法索引，纯文本资料不受影响

## 4. Ollama — 本地推理服务

**下载地址**: https://ollama.ai/download

**版本要求**: 0.1.20+

**操作系统**: macOS、Windows 10+、Linux

**启动服务**:
```bash
ollama serve
```

默认监听 http://localhost:11434

## 模型文件清单

| 模型 | 大小 | 必需 | 用途 |
|------|------|------|------|
| qwen2.5:7b | ~4GB | 推荐安装 | 本地摘要 |
| bge-small-zh-v1.5 | ~60MB | 必须 | 向量嵌入 |
| PaddleOCR 2.7 | ~130MB | 可选 | OCR 识别 |
| Ollama | ~100MB | 推荐安装 | 本地推理 |

**总大小**: 约 200MB（不含 qwen2.5:7b）

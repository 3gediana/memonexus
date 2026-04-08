# 模型配置说明

本项目使用以下本地模型，需要手动下载：

## 1. Qwen2.5 (Ollama)

用于知识库摘要生成。

```bash
# 安装 Ollama: https://ollama.ai
ollama pull qwen2.5
```

## 2. PaddleOCR

用于 PDF/图片文字识别。

**下载地址**: https://github.com/PaddlePaddle/PaddleOCR/blob/release/2.7/doc/doc_ch/models_list.md

**安放路径**: `知识库/.models/paddleocr-models/whl/`

需要模型:
- `ch_PP-OCRv4_det_infer` (文本检测)
- `ch_PP-OCRv4_rec_infer` (文本识别)
- `ch_ppocr_mobile_v2.0_cls_infer` (方向分类)

## 3. BGE-small-zh-v1.5

用于中文向量嵌入。

**Hugging Face**: https://huggingface.co/BAAI/bge-small-zh-v1.5

**ModelScope**: https://modelscope.cn/models/Xorbits/bge-small-zh-v1.5

**安放路径**: `知识库/.models/bge-small-zh-v1.5/`

下载后目录结构:

```
知识库/.models/bge-small-zh-v1.5/
├── config.json
├── model.onnx
├── tokenizer.json
├── tokenizer_config.json
├── vocab.txt
└── ...
```

## 4. ParseFlowMCP (可选)

用于高级文档解析。

**安放路径**: `知识库/.models/parseflow-mcp/`

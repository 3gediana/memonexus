# 知识库系统 - PaddleOCR 安装指南

## 概述

本知识库系统现在支持使用 PaddleOCR 进行本地 OCR 识别，不依赖任何外部 MCP 服务。

## 环境要求

- Python 3.8 或更高版本
- NVIDIA 显卡（推荐）或 CPU
- 显存 4GB 以上（使用 GPU 时）

## 安装步骤

### 1. 安装 Python

如果还没有安装 Python，可以从官网下载：https://www.python.org/downloads/

或者使用 Anaconda：https://www.anaconda.com/download

### 2. 安装 PaddlePaddle（GPU 版本）

**NVIDIA 显卡用户（推荐）：**

```bash
pip install paddlepaddle-gpu -i https://pypi.tuna.tsinghua.edu.cn/simple
```

**仅 CPU 用户：**

```bash
pip install paddlepaddle -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3. 安装 PaddleOCR

```bash
pip install paddleocr -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 4. 验证安装

运行以下命令测试 OCR：

```bash
python G:/知识库/.scripts/core/ocr-helper.py --help
```

或者直接用 Python 测试：

```python
from paddleocr import PaddleOCR
ocr = PaddleOCR(use_angle_cls=True, lang='ch', use_gpu=True)
result = ocr.ocr("测试图片.jpg", cls=True)
for line in result[0]:
    print(line[1][0])
```

## 配置说明

编辑 `G:/知识库/.scripts/config.json` 文件：

```json
{
  "ocr": {
    "enabled": true,           // 是否启用 OCR
    "provider": "paddleocr",   // OCR 提供商
    "pythonScript": "G:/知识库/.scripts/core/ocr-helper.py",  // OCR 脚本路径
    "pythonPath": "auto"       // Python 命令路径，"auto"表示自动查找
  },
  "indexer": {
    "concurrency": 5,  // 并发索引文件数
    "batchSize": 10    // 每批处理的文件数
  }
}
```

## 常见问题

### 1. GPU 无法识别

确保已安装最新的 NVIDIA 驱动，并安装了对应 CUDA 版本的 PaddlePaddle。

检查 CUDA 版本：
```bash
nvidia-smi
```

### 2. 内存不足

如果遇到内存错误，可以尝试：
- 减少并发数（修改 config.json 中的 `concurrency`）
- 使用 CPU 模式（修改 `use_gpu=False`）

### 3. 识别准确率低

确保：
- 图片清晰度足够（建议 300DPI 以上）
- 文字方向正确（PaddleOCR 支持自动旋转）
- 背景不要太复杂

## 支持的文件格式

### 直接 OCR 的文件：
- .jpg, .jpeg
- .png
- .bmp

### 文本提取失败时自动降级 OCR：
- .pdf（扫描版）
- .doc（旧版 Word）
- 其他 Office 文档

## 性能参考

基于 RTX 5060 8G 配置：

| 文档类型 | 速度 |
|----------|------|
| 普通扫描 PDF（1 页） | ~0.5-1 秒 |
| 密集文字 PDF（1 页） | ~1-2 秒 |
| 整本书（100 页） | ~1-2 分钟 |

## 卸载

如需卸载 PaddleOCR：

```bash
pip uninstall paddlepaddle-gpu paddleocr
```

## 相关链接

- PaddleOCR GitHub: https://github.com/PaddlePaddle/PaddleOCR
- PaddlePaddle 文档：https://www.paddlepaddle.org.cn/documentation

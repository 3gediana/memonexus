# Memonexus

> A lightweight long-term memory system for AI Agents

**Memonexus** 是一个为 AI Agent 设计的长程记忆系统，解决 Agent 的**记忆存储**和**知识储备不足**问题。

## 核心能力

- **记忆存储**：对话结束自动提取关键信息，多 Key 分类存储
- **记忆检索**：基于图关系的智能召回，支持跨 Key 关联
- **关联推理**：自动发现记忆间的语义关联，边强度动态校准
- **知识库**：本地文档索引，支持 RAG 风格知识注入

## 项目结构

```
memonexus/
├── 记忆库/                    # 后端核心
│   ├── src/
│   │   ├── agents/          # Agent 系统（Routing/Key/Association）
│   │   ├── api/             # FastAPI 接口
│   │   ├── db/             # SQLite 存储
│   │   └── tools/           # 检索/聚类工具
│   └── config.json.example
│
├── 知识库/                    # 本地知识库
│   ├── .scripts/            # 索引脚本
│   └── MODELS.md           # 模型配置说明
│
├── web-app/                  # Web 演示界面
└── requirements.txt
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置

```bash
cp 记忆库/config.json.example 记忆库/config.json
# 编辑填入你的 API Key
```

### 3. 启动服务

```bash
cd 记忆库 && python -m uvicorn src.api.server:app --reload
```

### 4. API 调用

```python
import requests

# 存储对话记忆
requests.post("http://localhost:8000/api/dialogue/clear", json={
    "instance": "default",
    "dialogue": [
        {"role": "user", "content": "我喜欢蓝色的衣服"},
        {"role": "assistant", "content": "好的，我记住了"}
    ]
})

# 召回相关记忆
requests.post("http://localhost:8000/api/recall", json={
    "instance": "default",
    "query": "用户偏好什么颜色"
})
```

## 技术栈

- **后端**：Python 3.10+ / FastAPI / SQLite
- **向量**：ONNX Runtime / BGE-small-zh-v1.5
- **前端**：React 19 / TypeScript / TailwindCSS

详见 [知识库/MODELS.md](知识库/MODELS.md)

## License

MIT

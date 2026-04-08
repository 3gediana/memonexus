# Memonexus

> A lightweight long-term memory framework for AI Agents

**Memonexus** 是一个为 AI Agent 设计的轻量化长程记忆框架，核心目标是解决 Agent 的**记忆存储**和**知识储备不足**问题。

不同于通用的聊天机器人，本项目专注于：

- **记忆管理**：Agent 运行过程中的关键信息自动提取、存储、检索
- **知识增强**：本地知识库检索，为 Agent 提供实时知识支持
- **关联推理**：跨会话的记忆关联与聚类，发现知识间的隐性联系

网页端仅作为演示和调试界面，真正的价值在于后端 API 的轻量化接入。

## 核心定位

```
┌─────────────────────────────────────────────────────┐
│                     Agent                            │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐             │
│  │ Planner │→ │ Memory  │→ │ Action │  → Tool Use  │
│  └─────────┘  └────┬────┘  └─────────┘             │
│                     ↓                               │
│            ┌────────────────┐                       │
│            │  Memonexus     │                       │
│            │  · 记忆存储     │                       │
│            │  · 知识检索     │                       │
│            │  · 关联推理     │                       │
│            └────────────────┘                       │
└─────────────────────────────────────────────────────┘
```

## 项目结构

```
memonexus/
├── 记忆库/                    # 后端核心（轻量化 API）
│   ├── src/
│   │   ├── agents/            # AI Agent 逻辑
│   │   │   ├── routing.py     # 路由 Agent
│   │   │   ├── key_agent.py  # Key 记忆提取
│   │   │   └── association.py # 关联 Agent
│   │   ├── api/               # FastAPI 接口
│   │   ├── db/                # SQLite 存储
│   │   └── tools/             # 检索/聚类工具
│   └── config.json.example
│
├── 知识库/                    # 本地知识库
│   ├── .scripts/              # 索引脚本
│   ├── .models/               # 本地模型（Qwen2.5, OCR, BGE）
│   └── MODELS.md              # 模型配置说明
│
├── web-app/                   # 调试界面（可选）
└── requirements.txt
```

## 核心能力

### 1. 记忆存储
- 对话结束后自动提取关键信息
- 重要性评分 + 权重机制
- 支持多 Key 分类存储

### 2. 记忆检索
- 语义向量检索（BGE embedding）
- 关键词混合检索
- 基于上下文的智能召回

### 3. 关联推理
- 自动发现跨 Key 的记忆关联
- 边强度校准
- 聚类合并机制

### 4. 知识库检索
- PDF/文档 OCR 解析
- 语义 chunk 切分
- RAG 风格的知识注入

## 快速接入 Agent

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

### 4. Agent 调用示例

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

## API 端点

| 端点 | 说明 |
|------|------|
| `POST /api/dialogue/clear` | 触发记忆存储 |
| `POST /api/recall` | 记忆语义检索 |
| `POST /api/keys` | 创建 Key |
| `GET /api/memories/{key}` | 获取 Key 下的记忆 |
| `GET /api/graph/{instance}` | 获取记忆图谱 |

## 技术栈

- **后端**：Python 3.10+ / FastAPI / SQLite
- **向量**：ONNX Runtime / BGE-small-zh-v1.5
- **前端**：React 19 / TypeScript / TailwindCSS
- **本地模型**：Qwen2.5 (Ollama) / PaddleOCR

详见 [知识库/MODELS.md](知识库/MODELS.md)

## License

MIT

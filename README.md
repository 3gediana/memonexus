# Memory Assistant (记忆助手)

基于 LLM 的智能记忆助手系统，支持对话记忆存储、检索和关联分析。

## 项目结构

```
memory-assistant/
├── 记忆库/                # 后端核心
│   ├── src/
│   │   ├── agents/        # AI Agent（Routing/Key/Association）
│   │   ├── api/           # FastAPI 服务端
│   │   ├── db/            # 数据库初始化与迁移
│   │   ├── system/        # 核心系统（LLM、事件总线、配置）
│   │   └── tools/         # 工具函数
│   └── config.json.example
├── 知识库/                # 本地知识库系统
│   ├── .scripts/          # 索引脚本
│   ├── .models/           # 模型文件（Qwen2.5, OCR, BGE）
│   └── config.json.example
├── web-app/               # React 前端
│   └── src/pages/ChatDemo/
├── requirements.txt
└── README.md
```

## 功能特性

- **智能对话**: 基于 LLM 的自然对话交互
- **记忆存储**: 自动提取关键信息存储到知识图谱
- **记忆关联**: 跨 Key 的记忆关联与聚类
- **记忆检索**: 语义检索 + 关键词检索混合模式
- **可视化**: 知识图谱可视化展示

## 技术栈

### 后端
- Python 3.10+
- FastAPI
- SQLite
- OpenAI API (DeepSeek/GLM)
- ONNX Runtime (向量计算)

### 前端
- React 19
- TypeScript
- Tailwind CSS
- D3.js / Cytoscape.js (图谱可视化)

### 本地模型依赖
详见 [知识库/MODELS.md](知识库/MODELS.md)

## 快速开始

### 1. 安装依赖

```bash
# Python 后端
pip install -r requirements.txt

# 前端
cd web-app && npm install
```

### 2. 本地模型准备

详见 [知识库/MODELS.md](知识库/MODELS.md)

### 3. 配置

```bash
# 复制配置模板
cp 记忆库/config.json.example 记忆库/config.json
cp 知识库/.scripts/config.json.example 知识库/.scripts/config.json

# 编辑 config.json 填入你的 API Key
```

### 4. 启动服务

```bash
# 后端 (端口 8000)
cd 记忆库 && python -m uvicorn src.api.server:app --reload

# 前端 (端口 5173)
cd web-app && npm run dev
```

## API 端点

- `POST /api/chat/stream/{instance}` - 流式对话
- `POST /api/dialogue/clear` - 清空对话（触发记忆存储）
- `GET /api/instances` - 列出所有实例
- `POST /api/keys` - 创建 Key

## License

MIT

# Memonexus - 记忆枢纽

> 图谱驱动的 Agent 长程记忆引擎 | GraphRAG × Louvain 聚类 × 多智能体协作

**Memonexus** 是一个基于**图谱检索增强生成（GraphRAG）**与**Louvain 社区发现算法**的 Agent 长程记忆系统，为大模型注入"持久记忆"，使其能够跨会话理解用户偏好、关联知识碎片、动态构建个人知识图谱。

---

## 核心特性

### 记忆图谱引擎
- **Louvain 社区发现**：对记忆节点进行实时社区聚类，自动发现语义关联簇
- **动态边校准**：基于共现频率与语义相似度动态调整记忆间关联强度
- **价值评估**：综合召回频次、时效性、情感权重计算记忆价值分数
- **GraphRAG 召回**：优先召回同社区记忆，兼顾跨社区关联推理

### 多智能体协作架构
- **DialogueAgent**：对话决策核心，支持流式 tool-use 循环，智能判断"存储/召回/直接回答"
- **KeyAgent**：Key 分类引擎，将记忆自动归入语义分类
- **AssociationAgent**：关联推理引擎，主动发现潜在记忆关联
- **CompressionAgent**：对话历史压缩，防止上下文膨胀
- **RoutingAgent**：动态路由，根据意图分发到不同处理管道

### 事件驱动的实时交互
- **SSE 事件流**：Agent 思考过程、tool-call 状态、记忆存储进度实时推送前端
- **AgentEventBus**：进程内事件总线，支持多 Agent 订阅/广播
- **EventBroadcaster**：跨 Agent 事件广播，实现观察者模式的全链路追踪

### 记忆生命周期管理
- **静息召回机制**：对话结束 45s 触发延迟召回，平衡即时响应与记忆巩固
- ** FreezeManager**：对话冻结队列，防止并发写入导致的状态撕裂
- **会话摘要压缩**：自动压缩长对话历史，保持上下文高效利用

### 本地知识库
- **混合检索**：关键词 + 向量双索引，支持 semantic chunk 分块
- **GraphRAG 注入**：知识库检索结果作为上下文注入对话
- **多格式支持**：PDF / TXT / Markdown 文档解析

---

## 系统架构

```
Memonexus
│
├── 记忆库（后端核心）
│   │
│   ├── ┌─────────────────────────────────────────┐
│   │   │          Agent 智能体层                 │
│   │   │  ┌──────────┐ ┌──────────┐ ┌────────┐ │
│   │   │  │ Dialogue │ │   Key    │ │Assoc.  │ │
│   │   │  │  Agent   │ │  Agent   │ │ Agent  │ │
│   │   │  └────┬─────┘ └────┬─────┘ └───┬────┘ │
│   │   │       └────────────┼───────────┘       │
│   │   │                    ▼                    │
│   │   │          AgentEventBus（事件总线）       │
│   │   └─────────────────────────────────────────┘
│   │
│   ├── ┌─────────────────────────────────────────┐
│   │   │          工具层（Tools）               │
│   │   │  save_recall │ recall_from_memory     │
│   │   │  build_edge │ calibrate_strength       │
│   │   │  cluster_memory │ assess_value        │
│   │   │  kb_search │ [30+ 工具函数]            │
│   │   └─────────────────────────────────────────┘
│   │
│   ├── ┌─────────────────────────────────────────┐
│   │   │          存储层（Storage）              │
│   │   │  ┌─────────────────────────────────┐  │
│   │   │  │   SQLite（记忆 + 图关系一体化）   │  │
│   │   │  │   nodes / edges / keys / 统计    │  │
│   │   │  └─────────────────────────────────┘  │
│   │   │  ┌─────────────────────────────────┐   │
│   │   │  │  BGE-small-zh-v1.5 (ONNX Runtime)│   │
│   │   │  │         向量嵌入引擎              │   │
│   │   │  └─────────────────────────────────┘   │
│   │   └─────────────────────────────────────────┘
│   │
│   └── ┌─────────────────────────────────────────┐
│       │          API 层（FastAPI）              │
│       │   65+ REST 端点 │ SSE 事件流           │
│       │   GET/POST/DELETE/PUT                  │
│       └─────────────────────────────────────────┘
│
├── 知识库（本地文档索引）
│   ├── .scripts/core/  ← TypeScript 索引核心
│   │   ├── vector-index.ts    (向量索引)
│   │   ├── keyword-index.ts   (jieba 关键词)
│   │   ├── chunker.ts         (语义分块)
│   │   └── mcp-server.ts      (MCP 服务)
│   └── 资料/              ← PDF/TXT 原始文档
│
└── web-app（React 19 可视化前端）
    ├── MemoryGraph/   ← D3 力导向图 + 社区聚类可视化
    ├── ChatDemo/      ← SSE 事件流实时展示
    ├── StatsDashboard/ ← 记忆统计仪表盘
    └── KnowledgeBase/ ← 知识库管理界面
```

---

## 核心技术亮点

| 技术点 | 实现方案 | 竞赛亮点 |
|--------|----------|----------|
| **GraphRAG** | 社区内优先召回 + 跨社区关联扩展 | 图谱检索比纯向量检索更可解释 |
| **Louvain 聚类** | cluster_engine.py 实时社区发现 | 自动揭示记忆间的隐性语义簇 |
| **多线程异步** | threading.Thread + asyncio.Queue 混合并发 | 记忆存储与对话响应互不阻塞 |
| **SSE 流式响应** | FastAPI StreamingResponse + 前端 TextDecoder | 打字机效果，实时感知 Agent 思维 |
| **上下文压缩** | CompressionAgent 对话历史摘要压缩 | 突破 token 上限，支持无限轮对话 |
| **记忆强度衰减** | 边校准算法动态调整关联权重 | 模拟人类记忆遗忘曲线 |
| **FreezeManager** | 对话冻结队列防止并发写入 | 高并发场景下数据一致性保证 |

---

## 快速开始

### 依赖安装
```bash
pip install -r requirements.txt
```

### 配置
```bash
cp 记忆库/config.json.example 记忆库/config.json
# 填入 DeepSeek API Key
```

### 启动
```bash
python start_server.py
```
一键启动后端（8000端口）+ 前端（5173端口）。

访问 http://localhost:5173 进入可视化界面。

---

## API 概览（65+ 端点）

| 模块 | 端点 | 说明 |
|------|------|------|
| **对话** | `POST /api/chat/stream/{id}` | SSE 流式对话 |
|  | `POST /api/dialogue/clear` | 触发记忆存储 |
| **记忆** | `GET /api/memory/list` | 分页记忆列表 |
|  | `GET /api/memory/stats` | 记忆统计 |
|  | `GET /api/memory/graph/nodes` | 图谱节点（含 cluster_id） |
|  | `GET /api/memory/graph/edges` | 图谱边（含强度） |
| **Key** | `GET /api/memory/keys` | 所有分类 |
| **知识库** | `POST /api/kb/search` | 混合检索 |
|  | `POST /api/kb/index` | 文档索引 |
| **监控** | `GET /api/monitor/stream` | SSE 实时监控流 |
| **实例** | `GET/POST /api/instances` | 多实例管理 |

---

## 技术栈

| 层级 | 技术选型 |
|------|----------|
| 后端核心 | Python 3.10+ / FastAPI / asyncio |
| 数据库 | SQLite（记忆 + 图关系一体化存储） |
| 向量引擎 | BGE-small-zh-v1.5 + ONNX Runtime |
| 知识库 | TypeScript / jieba / Node.js 索引脚本 |
| 前端 | React 19 / TypeScript / TailwindCSS / Vite |
| 图谱可视化 | react-force-graph-2d + D3-force |
| 事件流 | Server-Sent Events (SSE) |

---

## 竞赛定位

本项目属于**人工智能应用**赛道，面向大模型 Agent 的"记忆缺失"痛点提出系统性解决方案。

核心技术壁垒：
1. **GraphRAG 召回策略**优于传统向量检索，具备可解释性
2. **Louvain 社区发现**实现无监督记忆聚类，无需预先定义类别
3. **多 Agent 协作管道**模拟人类认知中的记忆存储/检索/关联全过程
4. **完整的产品形态**：从 CLI 对话到 Web 可视化图谱，具备直接演示能力

---

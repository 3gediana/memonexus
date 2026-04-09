# Memonexus

> A lightweight long-term memory system for AI Agents

**Memonexus** 是一个为 AI Agent 设计的长程记忆系统，解决 Agent 的**记忆存储**和**知识储备不足**问题。

## 核心能力

- **记忆存储**：对话结束自动提取关键信息，多 Key 分类存储
- **记忆检索**：基于图关系的智能召回，支持跨 Key 关联
- **关联推理**：自动发现记忆间的语义关联，边强度动态校准
- **知识库**：本地文档索引，支持 RAG 风格知识注入
- **事件流**：SSE 实时推送 Agent 工作状态到前端

## 项目结构

```
memonexus/
├── 记忆库/                              # 后端核心
│   ├── src/
│   │   ├── agents/                     # Agent 系统
│   │   │   ├── association.py          #   关联推理 Agent
│   │   │   ├── compression.py          #   记忆压缩 Agent
│   │   │   ├── dialogue.py             #   对话 Agent（流式解析 [TOOL]）
│   │   │   ├── key_agent.py            #   Key 分类 Agent
│   │   │   └── routing.py             #   路由 Agent
│   │   ├── api/                        # FastAPI 接口
│   │   │   └── server.py              #   65+ API 端点、SSE 事件流
│   │   ├── db/                         # 数据库层
│   │   │   ├── init.py                #   Neo4j/SQLite 初始化
│   │   │   ├── migrate.py             #   迁移工具
│   │   │   └── migrate_*.py           #   各类迁移脚本
│   │   ├── system/                     # 系统核心
│   │   │   ├── config.py             #   配置加载
│   │   │   ├── context.py             #   上文管理
│   │   │   ├── debug.py               #   调试工具
│   │   │   ├── event_bus.py           #   事件总线（SSE 推送）
│   │   │   ├── event_broadcaster.py   #   事件广播
│   │   │   ├── fingerprint.py         #   指纹生成
│   │   │   ├── freeze.py              #   对话冻结机制
│   │   │   ├── llm_client.py          #   LLM 调用封装
│   │   │   ├── logger.py              #   日志系统
│   │   │   ├── main.py                #   核心调度
│   │   │   ├── recall_flow.py         #   召回流程
│   │   │   ├── recall_timer.py        #   召回计时
│   │   │   ├── retry.py               #   重试机制
│   │   │   ├── scheduler.py           #   任务调度
│   │   │   └── storage_flow.py        #   存储流程
│   │   ├── tools/                      # 工具集
│   │   │   ├── association_scorer.py  #   关联评分
│   │   │   ├── cluster_engine.py      #   聚类引擎
│   │   │   ├── cluster_service.py     #   聚类服务
│   │   │   ├── edge_calibrator.py     #   边校准
│   │   │   ├── edge_tools.py          #   边操作工具
│   │   │   ├── kb_chunker.py          #   知识库分块
│   │   │   ├── kb_extractor.py        #   知识库提取
│   │   │   ├── kb_keyword.py          #   关键词索引
│   │   │   ├── kb_tools.py            #   知识库 API tools
│   │   │   ├── kb_vector.py           #   向量索引
│   │   │   ├── key_tools.py           #   Key 操作
│   │   │   ├── memory_space_tools.py  #   记忆空间
│   │   │   ├── memory_tools.py        #   记忆 CRUD
│   │   │   ├── monitor.py             #   监控
│   │   │   ├── preference_tracker.py  #   偏好追踪
│   │   │   ├── query_tools.py         #   查询工具
│   │   │   ├── recall_tools.py        #   召回工具
│   │   │   ├── routing_tools.py       #   路由工具
│   │   │   ├── session_tools.py       #   会话工具
│   │   │   ├── sub_tools.py           #   订阅工具
│   │   │   ├── topk_calculator.py     #   TopK 计算
│   │   │   ├── value_assessor.py      #   价值评估
│   │   │   ├── visibility_tools.py    #   可见性控制
│   │   │   └── weight_tools.py        #   权重调整
│   │   ├── demo/                       # Demo 脚本
│   │   │   ├── __main__.py
│   │   │   ├── demo_tools.py
│   │   │   ├── orchestrator.py
│   │   │   └── sim_user.py
│   │   └── ui/                         # CLI 界面
│   │       ├── components/
│   │       └── styles.py
│   ├── instances/                      # 实例数据
│   └── config.json.example             # 配置模板
│
├── 知识库/                              # 本地知识库
│   ├── .scripts/                       # 索引脚本
│   │   ├── core/                      #   核心模块
│   │   │   ├── chunker.ts            #     分块器
│   │   │   ├── content-store.ts       #     内容存储
│   │   │   ├── database.ts           #     数据库
│   │   │   ├── extractor.ts          #     内容提取
│   │   │   ├── fingerprint.ts        #     指纹生成
│   │   │   ├── jieba-keyword.py      #     jieba 关键词
│   │   │   ├── keyword-index.ts      #     关键词索引
│   │   │   ├── vector-index.ts       #     向量索引
│   │   │   ├── query-dispatcher.ts   #     查询分发
│   │   │   ├── mcp-server.ts         #     MCP 服务
│   │   │   ├── ocr-helper.py         #     OCR 辅助
│   │   │   ├── lru-cache.ts          #     LRU 缓存
│   │   │   └── logger.ts             #     日志
│   │   ├── backup/                    #   备份
│   │   ├── ollama-adapter/           #   Ollama 适配器
│   │   ├── batch-indexer.js          #   批量索引
│   │   └── reindex-text.js           #   重建索引
│   ├── 资料/                           # 参考资料（PDF）
│   ├── CLAUDE.md
│   ├── INDEX.md
│   ├── MODELS.md
│   └── README.md
│
├── web-app/                             # Web 演示界面
│   ├── public/                         # 静态资源
│   ├── src/
│   │   ├── assets/                    #   图片资源
│   │   ├── components/                #   公共组件
│   │   │   ├── Header/
│   │   │   └── Sidebar/
│   │   ├── constants/                 #   常量定义
│   │   ├── hooks/                     #   自定义 Hooks
│   │   │   └── useStreamConnection.ts #     SSE 流连接
│   │   ├── mock/                      #   Mock 数据
│   │   ├── pages/                     #   页面
│   │   │   ├── AgentFlow/            #     Agent 流程图
│   │   │   ├── ChatDemo/             #     对话演示（SSE 事件流）
│   │   │   ├── KnowledgeBase/        #     知识库管理
│   │   │   ├── MemoryGraph/          #     记忆图谱
│   │   │   ├── MemoryList/           #     记忆列表
│   │   │   ├── Settings/             #     设置
│   │   │   ├── StatsDashboard/       #     统计仪表盘
│   │   │   └── Sub/                  #     订阅管理
│   │   ├── utils/                     #   工具函数
│   │   │   └── EventBus.ts           #     事件总线
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── package.json
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── vite.config.ts
│
├── DESIGN_DOC.md                        # 系统设计文档
├── start_server.py                      # 启动脚本
├── .gitignore
├── README.md
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
python start_server.py
# 或手动启动：cd 记忆库 && python -m uvicorn src.api.server:app --reload
```

### 4. 启动前端

```bash
cd web-app && npm install && npm run dev
```

## API 端点

### 对话
| 端点 | 说明 |
|------|------|
| `POST /api/dialogue/clear` | 触发记忆存储 |
| `GET /api/dialogue/messages` | 获取对话消息 |
| `POST /api/chat/stream/{instance_id}` | SSE 流式对话 |

### 记忆
| 端点 | 说明 |
|------|------|
| `GET /api/memory/list` | 获取记忆列表 |
| `GET /api/memory/{fingerprint}` | 获取单条记忆 |
| `PUT /api/memory/{fingerprint}` | 更新记忆 |
| `DELETE /api/memory/{fingerprint}` | 删除记忆 |
| `GET /api/memory/keys` | 获取所有 Key |
| `GET /api/memory/stats` | 记忆统计 |

### 图谱
| 端点 | 说明 |
|------|------|
| `GET /api/memory/graph/nodes` | 获取图谱节点 |
| `GET /api/memory/graph/edges` | 获取图谱边 |
| `POST /api/edges` | 创建关联边 |
| `DELETE /api/edges` | 删除关联边 |

### 知识库
| 端点 | 说明 |
|------|------|
| `POST /api/kb/search` | 知识库搜索 |
| `POST /api/kb/index` | 建立索引 |
| `GET /api/kb/indexed` | 已索引文件列表 |
| `GET /api/kb/stats` | 知识库统计 |

### 实例 & 配置
| 端点 | 说明 |
|------|------|
| `GET /api/instances` | 获取所有实例 |
| `POST /api/instances` | 创建实例 |
| `GET /api/config` | 获取配置 |
| `POST /api/config` | 更新配置 |
| `GET /api/monitor/stream` | SSE 监控流 |

## 技术栈

- **后端**：Python 3.10+ / FastAPI / SQLite / Neo4j
- **向量**：ONNX Runtime / BGE-small-zh-v1.5
- **知识库**：TypeScript / jieba / Node.js 索引脚本
- **前端**：React 19 / TypeScript / TailwindCSS / Vite

详见 [知识库/MODELS.md](知识库/MODELS.md)

## License

MIT

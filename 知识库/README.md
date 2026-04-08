# 知识库系统

本地知识库检索系统，为 Agent 提供实时知识支持。

## 目录结构

```
知识库/
├── 资料/              # 📌 资料必须放在这里才能被索引！
├── .scripts/          # 索引脚本
├── .models/           # 本地模型
├── .index/            # 索引数据库（自动生成）
├── .chunks/           # 文档切分（自动生成）
└── CLAUDE.md          # Claude AI 使用指南
```

## 资料入库规则

**⚠️ 重要：资料必须放到 `知识库/资料/` 目录下才能被索引！**

1. 将 PDF、Markdown、TXT 等文件放入 `资料/` 目录
2. 运行索引脚本：`node .scripts/update-index-md.js`
3. 查看待索引文件：`cat INDEX.md`
4. 索引单个文件：`kb_index_file("路径")`
5. 索引整个目录：`kb_index_directory("资料/")`

## MCP 工具使用

### MCP Server 启动

```bash
cd 知识库/.scripts/ollama-adapter
npm install
npm start
```

MCP Server 提供以下工具：

| 工具 | 说明 |
|------|------|
| `kb_search` | 混合搜索（关键词 + 语义） |
| `kb_sans_search` | 搜索 + 本地 AI 总结（节省 token） |
| `kb_index_file` | 索引单个文件 |
| `kb_index_directory` | 索引整个目录 |
| `kb_get_stats` | 查看索引状态 |
| `kb_list_indexed` | 列出已索引文件 |

### Sans 模式（节省 token）

当用户输入 `sans(问题)` 格式时，调用 `kb_sans_search`：

```
kb_sans_search({
    query: "核心关键词",
    summaryInstruction: "告诉本地模型重点总结哪些方面",
    topK: 5
})
```

本地模型（Qwen2.5）会先对检索结果进行总结，再返回给你。

## 前端 Agent 对接规则

**⚠️ 在网页对话或 Agent 对话中激活知识库功能：**

消息中必须包含 **"知识库"** 三个字！

示例：
- ✅ `"帮我查一下知识库中关于Python装饰器的资料"`
- ✅ `"知识库搜索：机器学习复习资料"`
- ❌ `"帮我查一下Python装饰器"` （不会激活 KB tools）

## 本地模型依赖

详见 [MODELS.md](MODELS.md)

- **Qwen2.5**: 本地总结模型（Ollama）
- **BGE-small-zh-v1.5**: 向量嵌入
- **PaddleOCR**: 文本识别

## CLAUDE.md 是什么？

`CLAUDE.md` 是给 Claude AI 看的使用指南，定义了：
- 知识库工具的使用流程
- Sans 模式的正确调用方式
- 禁止使用的工具（必须通过 MCP）

如果你使用其他 AI，可以参考这个文件来编写对应的提示词。

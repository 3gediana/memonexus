# 知识库系统

你正在知识库目录下。**检索资料的唯一方式是 MCP `kb_*` 工具，绝对禁止使用任何其他工具。**

## 绝对禁止的工具
**禁止使用：** Task、Glob、Grep、Read、Write、Edit、Bash（除非运行 update-index-md.js）

## 用户提问处理流程

### 普通提问
1. 调用 `kb_search(query, topK)` 搜索
2. 根据返回结果组织回答
3. 注明来源文件名和分数

### Sans 模式（节省 token）- 高优先级！
**当用户输入 `sans(问题)` 格式时，必须调用 `kb_sans_search` 工具！**

调用格式：
```
kb_sans_search({
    query: "从问题中提取的核心关键词",
    summaryInstruction: "分析用户真正想了解什么，告诉本地模型重点总结哪些方面",
    topK: 5  // 必须指定，获取更多上下文
})
```

**不要**自己先搜索再回答，**必须**使用 `kb_sans_search`！

**示例：**
- 用户：`sans(Python 装饰器怎么用？)`
- 正确调用：`kb_sans_search({ query: "Python 装饰器", summaryInstruction: "用户想了解装饰器的使用方法和语法", topK: 5 })`
- 错误做法：调用 `kb_search` 然后自己总结，或者不传 topK 参数

## 新文件入库流程
1. 运行 `node "G:/知识库/.scripts/update-index-md.js"`
2. 读取 `INDEX.md` 查看待索引文件
3. 调用 `kb_index_file(filePath)` 或 `kb_index_directory(dirPath)` 索引
4. 再运行脚本确认清空

## MCP 工具列表
| 工具 | 用途 |
|------|------|
| `kb_search` | 混合搜索（关键词 + 语义） |
| `kb_keyword_search` | 纯关键词搜索 |
| `kb_semantic_search` | 纯语义搜索 |
| `kb_sans_search` | 搜索 + 本地 AI 总结（节省 token，sans 模式专用） |
| `kb_index_file` | 索引单个文件 |
| `kb_index_directory` | 索引整个目录 |
| `kb_reindex_all` | 增量更新 |
| `kb_reindex_file` | 重新索引单文件 |
| `kb_get_stats` | 查看状态 |
| `kb_list_indexed` | 列出已索引文件 |
| `kb_remove_file` | 删除索引 |

**记住：普通提问 = `kb_search`，sans 模式 = `kb_sans_search`（必须调用）！**

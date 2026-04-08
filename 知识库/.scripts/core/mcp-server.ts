import * as path from "path";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

import { FingerprintManager } from "./fingerprint";
import { Chunker } from "./chunker";
import { KeywordIndexer } from "./keyword-index";
import { VectorIndexer } from "./vector-index";
import { ContentStore } from "./content-store";
import { ReExtractor } from "./extractor";
import { QueryDispatcher } from "./query-dispatcher";

const TOOLS = [
  {
    name: "kb_search",
    description: "混合搜索知识库（关键词+语义），返回最相关的文本块",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "搜索查询文本" },
        topK: { type: "number", description: "返回结果数量，默认5" },
      },
      required: ["query"],
    },
  },
  {
    name: "kb_keyword_search",
    description: "纯关键词搜索知识库",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "搜索关键词" },
        topK: { type: "number", description: "返回结果数量，默认5" },
      },
      required: ["query"],
    },
  },
  {
    name: "kb_semantic_search",
    description: "纯语义搜索知识库（理解意思，不只匹配词）",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "搜索查询文本" },
        topK: { type: "number", description: "返回结果数量，默认5" },
      },
      required: ["query"],
    },
  },
  {
    name: "kb_index_file",
    description: "将文件添加到知识库索引",
    inputSchema: {
      type: "object",
      properties: {
        filePath: { type: "string", description: "文件完整路径" },
      },
      required: ["filePath"],
    },
  },
  {
    name: "kb_index_directory",
    description: "索引整个目录下的所有文件",
    inputSchema: {
      type: "object",
      properties: {
        dirPath: { type: "string", description: "目录路径" },
        recursive: { type: "boolean", description: "是否递归子目录，默认true" },
      },
      required: ["dirPath"],
    },
  },
  {
    name: "kb_reindex_file",
    description: "强制重新索引指定文件",
    inputSchema: {
      type: "object",
      properties: {
        filePath: { type: "string", description: "文件完整路径" },
      },
      required: ["filePath"],
    },
  },
  {
    name: "kb_reindex_all",
    description: "增量更新：扫描资料目录，处理新增和修改的文件",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "kb_get_chunk",
    description: "获取单个文本块的内容",
    inputSchema: {
      type: "object",
      properties: {
        chunkId: { type: "string", description: "块ID，格式：指纹-序号" },
      },
      required: ["chunkId"],
    },
  },
  {
    name: "kb_get_document",
    description: "获取文档信息及所有文本块",
    inputSchema: {
      type: "object",
      properties: {
        fingerprint: { type: "string", description: "文件指纹（16位MD5）" },
      },
      required: ["fingerprint"],
    },
  },
  {
    name: "kb_list_indexed",
    description: "列出所有已索引的文件",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "kb_list_pending",
    description: "列出待索引的文件",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "kb_get_stats",
    description: "获取知识库统计信息",
    inputSchema: { type: "object", properties: {} },
  },
  {
    name: "kb_remove_file",
    description: "从知识库中删除指定文件的索引（保留原始文件）",
    inputSchema: {
      type: "object",
      properties: {
        fingerprint: { type: "string", description: "文件指纹（16位MD5），可通过 kb_list_indexed 获取" },
      },
      required: ["fingerprint"],
    },
  },
];

async function main() {
  // 初始化各模块
  const fm = new FingerprintManager();
  const chunker = new Chunker();
  const kwIndexer = new KeywordIndexer();
  const vecIndexer = new VectorIndexer();
  const store = new ContentStore();
  const extractor = new ReExtractor(fm, chunker, kwIndexer, vecIndexer, store);
  const dispatcher = new QueryDispatcher(fm, kwIndexer, vecIndexer, store, extractor);

  // 懒加载：不在启动时初始化向量模型，首次使用时才加载
  await extractor.init().catch(() => {
    // 模型加载失败不阻塞服务器启动，语义搜索不可用时会返回错误
  });

  const server = new Server(
    { name: "knowledge-base", version: "1.0.0" },
    { capabilities: { tools: {} } }
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => ({ tools: TOOLS }));

  server.setRequestHandler(CallToolRequestSchema, async (req) => {
    const { name, arguments: args = {} } = req.params;

    try {
      let result: any;

      const a = args as Record<string, any>;
      switch (name) {
        case "kb_search":
          result = await dispatcher.search(a.query as string, { topK: a.topK ?? 5 });
          break;
        case "kb_keyword_search":
          result = await dispatcher.keywordSearch(a.query as string, a.topK ?? 5);
          break;
        case "kb_semantic_search":
          result = await dispatcher.semanticSearch(a.query as string, a.topK ?? 5);
          break;
        case "kb_index_file":
          result = await extractor.extractFile(a.filePath as string);
          break;
        case "kb_index_directory":
          result = await extractor.extractDirectory(a.dirPath as string, a.recursive !== false);
          break;
        case "kb_reindex_file": {
          const fp = fm.compute(path.resolve(a.filePath as string));
          await extractor.reindex(fp);
          result = { success: true };
          break;
        }
        case "kb_reindex_all":
          result = await extractor.incrementalUpdate();
          break;
        case "kb_get_chunk":
          result = store.load(a.chunkId as string);
          if (!result) throw new Error(`块不存在: ${a.chunkId}`);
          break;
        case "kb_get_document": {
          const chunks = store.loadByFingerprint(a.fingerprint as string);
          const entry = fm.getIndexedFiles().find(f => f.fingerprint === a.fingerprint);
          result = {
            fingerprint: a.fingerprint,
            fileName: entry ? path.basename(entry.path) : a.fingerprint,
            filePath: entry?.path ?? "",
            size: entry?.size ?? 0,
            chunkCount: chunks.length,
            chunks,
          };
          break;
        }
        case "kb_list_indexed":
          result = fm.getIndexedFiles();
          break;
        case "kb_list_pending":
          result = fm.getPendingFiles();
          break;
        case "kb_get_stats":
          result = await dispatcher.getStats();
          break;
        case "kb_remove_file": {
          const fp = a.fingerprint as string;
          store.remove(fp);
          vecIndexer.remove(fp);
          fm.removeRecord(fp);
          // 清除缓存
          dispatcher.clearCache();
          result = { success: true, message: `已删除指纹 ${fp} 的索引` };
          break;
        }
        default:
          throw new Error(`未知工具: ${name}`);
      }

      return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
      };
    } catch (e: any) {
      return {
        content: [{ type: "text", text: `错误: ${e.message}` }],
        isError: true,
      };
    }
  });

  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch(console.error);

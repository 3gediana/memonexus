import * as path from "path";
import { FingerprintManager } from "./fingerprint";
import { KeywordIndexer } from "./keyword-index";
import { VectorIndexer } from "./vector-index";
import { ContentStore } from "./content-store";
import { ReExtractor } from "./extractor";
import { LRUCache } from "./lru-cache";

export interface SearchOptions {
  topK?: number;
  useKeyword?: boolean;
  useVector?: boolean;
  minScore?: number;
}

export interface SearchResult {
  chunkId: string;
  text: string;
  score: number;
  source: string;
  page?: number;
  keywords?: string[];
}

export class QueryDispatcher {
  // 查询结果缓存，避免重复搜索相同查询
  private queryCache = new LRUCache<string, SearchResult[]>(100);
  // 指纹到文件信息的缓存，避免重复遍历
  private fingerprintCache = new LRUCache<string, { path: string; name: string }>(500);

  constructor(
    private fm: FingerprintManager,
    private kwIndexer: KeywordIndexer,
    private vecIndexer: VectorIndexer,
    private store: ContentStore,
    private extractor: ReExtractor
  ) {
    // 预加载指纹缓存
    this.warmFingerprintCache();
  }

  private warmFingerprintCache(): void {
    const indexed = this.fm.getIndexedFiles();
    for (const file of indexed.slice(0, 500)) {
      this.fingerprintCache.set(file.fingerprint, {
        path: file.path,
        name: path.basename(file.path),
      });
    }
  }

  async search(query: string, options: SearchOptions = {}): Promise<SearchResult[]> {
    const { topK = 5, useKeyword = true, useVector = true, minScore = 0.5 } = options;

    // 先查缓存
    const cacheKey = `${query}:${topK}:${useKeyword}:${useVector}:${minScore}`;
    if (this.queryCache.has(cacheKey)) {
      return this.queryCache.get(cacheKey)!;
    }

    const merged = new Map<string, number>();

    // 并行搜索
    const [kwIds, vecResults] = await Promise.all([
      useKeyword ? Promise.resolve(this.kwIndexer.search(query)) : Promise.resolve([]),
      useVector ? this.vecIndexer.search(query, topK * 2) : Promise.resolve([]),
    ]);

    // 加入向量结果
    for (const r of vecResults) {
      merged.set(r.chunkId, r.score);
    }

    // 加入关键词结果
    for (const id of kwIds) {
      if (merged.has(id)) {
        merged.set(id, merged.get(id)! + 0.1);
      } else {
        merged.set(id, 0.7);
      }
    }

    // 按分数排序，过滤低分
    const sorted = Array.from(merged.entries())
      .filter(([, score]) => score >= minScore)
      .sort((a, b) => b[1] - a[1])
      .slice(0, topK);

    let results: SearchResult[];

    if (sorted.length === 0) {
      results = await this.autoExtractAndRetry(query, options);
    } else {
      // 批量读取内容
      const chunks = this.store.loadBatch(sorted.map(([id]) => id));
      results = sorted.map(([id, score]) => {
        const chunk = chunks.find(c => c.id === id);
        const fileInfo = this.fingerprintCache.get(id.split("-").slice(0, -1).join("-"));
        return {
          chunkId: id,
          text: chunk?.text ?? "",
          score,
          source: fileInfo?.name ?? id.split("-").slice(0, -1).join("-"),
          page: chunk?.page,
          keywords: chunk?.keywords,
        };
      }).filter(r => r.text);
    }

    // 缓存结果
    this.queryCache.set(cacheKey, results);
    return results;
  }

  async keywordSearch(query: string, topK = 5): Promise<SearchResult[]> {
    return this.search(query, { topK, useKeyword: true, useVector: false });
  }

  async semanticSearch(query: string, topK = 5): Promise<SearchResult[]> {
    return this.search(query, { topK, useKeyword: false, useVector: true });
  }

  async getStats(): Promise<{
    totalFiles: number;
    totalChunks: number;
    indexedFiles: number;
    pendingFiles: number;
  }> {
    const indexed = this.fm.getIndexedFiles();
    const pending = this.fm.getPendingFiles();
    const totalChunks = indexed.reduce((sum, f) => sum + (f.chunksCount ?? 0), 0);
    return {
      totalFiles: indexed.length + pending.length,
      totalChunks,
      indexedFiles: indexed.length,
      pendingFiles: pending.length,
    };
  }

  private async autoExtractAndRetry(query: string, options: SearchOptions): Promise<SearchResult[]> {
    const pending = this.fm.getPendingFiles();
    if (pending.length === 0) return [];
    for (const file of pending.slice(0, 10)) {
      await this.extractor.extractFile(file);
    }
    // 更新缓存
    this.warmFingerprintCache();
    // 重试一次，不再递归
    return this.search(query, { ...options, minScore: 0 });
  }

  // 清除缓存（当索引更新时调用）
  clearCache(): void {
    this.queryCache.clear();
    this.warmFingerprintCache();
  }
}

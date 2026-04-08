import * as fs from "fs";
import * as path from "path";
import { Index, MetricKind, ScalarKind, Matches } from "usearch";

const INDEX_DIR = path.resolve(__dirname, "../../../.index/vector");
const MODEL_CACHE = path.resolve(__dirname, "../../../.models/bge-small-zh-v1.5");
const MODEL_NAME = "Xenova/bge-small-zh-v1.5";
const DIMENSION = 512;

// 全局 HNSW 索引实例
let globalIndex: Index | null = null;

interface MetaFile {
  fingerprint: string;
  chunkCount: number;
  dimension: number;
  ids: string[];
  createdAt: string;
}

// 将 chunkId 映射为 BigInt key
function chunkIdToKey(str: string): bigint {
  // 简单的 hash 算法
  let hash = 5381n;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5n) + hash) + BigInt(str.charCodeAt(i));
    hash = hash & 0x7FFFFFFFn; // 转为正数
  }
  return hash;
}

export class VectorIndexer {
  private pipeline: any = null;
  // 本地索引映射：chunkId -> BigInt key
  private idToKey = new Map<string, bigint>();
  private keyToId = new Map<bigint, string>();
  // 缓存 chunkId -> vector 用于调试和备份
  private vectorCache = new Map<string, number[]>();

  async init(): Promise<void> {
    const { pipeline, env } = await import("@xenova/transformers");
    env.cacheDir = MODEL_CACHE;
    env.allowLocalModels = true;
    env.allowRemoteModels = false;
    this.pipeline = await pipeline("feature-extraction", MODEL_NAME);

    // 懒加载 HNSW 索引
    this.loadOrCreateIndex();
  }

  private loadOrCreateIndex(): void {
    // 总是从备份恢复，不依赖 usearch 的 save/load（Windows 兼容性问题）
    console.log("[VectorIndexer] 从备份恢复索引");
    this.restoreFromBackup();

    if (globalIndex === null) {
      globalIndex = new Index({
        dimensions: DIMENSION,
        metric: MetricKind.Cos,
        quantization: ScalarKind.F32,
        connectivity: 16,
        expansion_add: 128,
        expansion_search: 64,
        multi: false,
      });
      console.log("[VectorIndexer] 创建新的 HNSW 索引");
    }
  }

  // 从备份的 vectors.json 文件恢复索引
  private restoreFromBackup(): void {
    if (!fs.existsSync(INDEX_DIR)) {
      console.log("[VectorIndexer] 备份目录不存在");
      return;
    }

    const shards = fs.readdirSync(INDEX_DIR).filter(f => fs.statSync(path.join(INDEX_DIR, f)).isDirectory());
    let totalLoaded = 0;

    for (const shard of shards) {
      const shardDir = path.join(INDEX_DIR, shard);
      const files = fs.readdirSync(shardDir).filter(f => f.endsWith(".vectors.json"));

      for (const file of files) {
        const fingerprint = file.replace(".vectors.json", "");
        this.loadToCache(fingerprint);
        totalLoaded++;
      }
    }

    if (totalLoaded > 0) {
      // 创建索引
      globalIndex = new Index({
        dimensions: DIMENSION,
        metric: MetricKind.Cos,
        quantization: ScalarKind.F32,
        connectivity: 16,
        expansion_add: 128,
        expansion_search: 64,
        multi: false,
      });

      // 将所有缓存向量添加到索引
      for (const [chunkId, vec] of this.vectorCache) {
        const key = chunkIdToKey(chunkId);
        const vecArray = new Float32Array(vec);
        globalIndex.add(key, vecArray);

        // 建立映射表
        this.idToKey.set(chunkId, key);
        this.keyToId.set(key, chunkId);
      }

      console.log(`[VectorIndexer] 从备份恢复 ${totalLoaded} 个文件，共 ${this.vectorCache.size} 个向量`);
    }
  }

  // 将向量加载到缓存（不添加到索引，索引在 restoreFromBackup 中统一创建）
  private loadToCache(fingerprint: string): void {
    const shard = fingerprint.slice(0, 2);
    const vecFile = path.join(INDEX_DIR, shard, `${fingerprint}.vectors.json`);
    if (!fs.existsSync(vecFile)) return;

    const vecs: Record<string, number[]> = JSON.parse(fs.readFileSync(vecFile, "utf-8"));
    for (const [id, vec] of Object.entries(vecs)) {
      this.vectorCache.set(id, vec);
    }
  }

  // 重建 key 映射
  private rebuildMapping(): void {
    this.idToKey.clear();
    this.keyToId.clear();
    for (const [chunkId] of this.vectorCache) {
      const key = chunkIdToKey(chunkId);
      this.idToKey.set(chunkId, key);
      this.keyToId.set(key, chunkId);
    }
  }

  isReady(): boolean {
    return this.pipeline !== null && globalIndex !== null;
  }

  async embed(text: string): Promise<number[]> {
    if (!this.pipeline) return [];
    const output = await this.pipeline(text, { pooling: "mean", normalize: true });
    return Array.from(output.data as Float32Array);
  }

  add(chunkId: string, vector: number[]): void {
    if (!globalIndex || vector.length !== DIMENSION) return;

    const key = chunkIdToKey(chunkId);
    const vecArray = new Float32Array(vector);

    try {
      // 检查是否已存在
      const exists = globalIndex.contains(key);
      if (exists) {
        globalIndex.remove(key);
      }

      globalIndex.add(key, vecArray);
      this.idToKey.set(chunkId, key);
      this.keyToId.set(key, chunkId);
      this.vectorCache.set(chunkId, vector);
    } catch (e) {
      console.error(`[VectorIndexer] 添加向量失败 ${chunkId}:`, e);
    }
  }

  addBatch(chunks: { id: string; vector: number[] }[]): void {
    for (const c of chunks) this.add(c.id, c.vector);
  }

  async search(query: string, topK: number): Promise<{ chunkId: string; score: number }[]> {
    if (!this.pipeline || !globalIndex) return [];

    const qv = await this.embed(query);
    if (qv.length === 0) return [];

    const qvArray = new Float32Array(qv);

    try {
      // usearch 搜索需要指定 threads 参数
      const results: Matches = globalIndex.search(qvArray, topK * 2, 0);

      const output: { chunkId: string; score: number }[] = [];
      for (let i = 0; i < results.keys.length; i++) {
        const key = results.keys[i];
        const chunkId = this.keyToId.get(key);
        if (chunkId && this.vectorCache.has(chunkId)) {
          output.push({
            chunkId,
            score: results.distances[i],
          });
        }
      }
      return output;
    } catch (e) {
      console.error("[VectorIndexer] 搜索失败:", e);
      return [];
    }
  }

  save(fingerprint: string): void {
    const shard = fingerprint.slice(0, 2);
    const dir = path.join(INDEX_DIR, shard);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    // 收集属于该指纹的块
    const ids = Array.from(this.idToKey.entries())
      .filter(([, key]) => this.keyToId.get(key)?.startsWith(fingerprint))
      .map(([id]) => id);

    const vecs: Record<string, number[]> = {};
    for (const id of ids) {
      const vec = this.vectorCache.get(id);
      if (vec) vecs[id] = vec;
    }

    // 保存向量数据作为备份（这是唯一持久化源）
    fs.writeFileSync(
      path.join(dir, `${fingerprint}.vectors.json`),
      JSON.stringify(vecs),
      "utf-8"
    );

    // 保存元数据
    const meta: MetaFile = {
      fingerprint,
      chunkCount: ids.length,
      dimension: DIMENSION,
      ids,
      createdAt: new Date().toISOString(),
    };
    fs.writeFileSync(
      path.join(dir, `${fingerprint}.meta.json`),
      JSON.stringify(meta, null, 2),
      "utf-8"
    );
  }

  load(fingerprint: string): void {
    const shard = fingerprint.slice(0, 2);
    const vecFile = path.join(INDEX_DIR, shard, `${fingerprint}.vectors.json`);
    if (!fs.existsSync(vecFile)) return;

    const vecs: Record<string, number[]> = JSON.parse(fs.readFileSync(vecFile, "utf-8"));
    for (const [id, vec] of Object.entries(vecs)) {
      this.vectorCache.set(id, vec);
      this.add(id, vec); // 重新添加到 HNSW 索引
    }
  }

  remove(fingerprint: string): void {
    const idsToRemove = Array.from(this.idToKey.entries())
      .filter(([, key]) => this.keyToId.get(key)?.startsWith(fingerprint))
      .map(([id]) => id);

    for (const id of idsToRemove) {
      const key = this.idToKey.get(id);
      if (key && globalIndex) {
        globalIndex.remove(key);
      }
      this.idToKey.delete(id);
      this.keyToId.delete(key!);
      this.vectorCache.delete(id);
    }

    const shard = fingerprint.slice(0, 2);
    const dir = path.join(INDEX_DIR, shard);
    for (const ext of ["vectors.json", "meta.json"]) {
      const f = path.join(dir, `${fingerprint}.${ext}`);
      if (fs.existsSync(f)) fs.unlinkSync(f);
    }
  }
}

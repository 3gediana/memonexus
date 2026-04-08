import * as fs from "fs";
import * as path from "path";
import type { Chunk } from "./chunker";
import { LRUCache } from "./lru-cache";

const CHUNKS_DIR = path.resolve(__dirname, "../../../.chunks");

interface ChunkFile {
  fingerprint: string;
  totalChunks: number;
  createdAt: string;
  chunks: Chunk[];
}

function getChunkFile(fingerprint: string): string {
  const shard = fingerprint.slice(0, 2);
  const dir = path.join(CHUNKS_DIR, shard);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  return path.join(dir, `${fingerprint}.json`);
}

export class ContentStore {
  // 使用 LRU 缓存，最多缓存 200 个文件，避免内存无限增长
  private cache = new LRUCache<string, ChunkFile>(200);

  private loadFile(fingerprint: string): ChunkFile | null {
    if (this.cache.has(fingerprint)) return this.cache.get(fingerprint)!;
    const file = getChunkFile(fingerprint);
    if (!fs.existsSync(file)) return null;
    const data: ChunkFile = JSON.parse(fs.readFileSync(file, "utf-8"));
    this.cache.set(fingerprint, data);
    return data;
  }

  save(fingerprint: string, chunks: Chunk[]): void {
    const data: ChunkFile = {
      fingerprint,
      totalChunks: chunks.length,
      createdAt: new Date().toISOString(),
      chunks,
    };
    fs.writeFileSync(getChunkFile(fingerprint), JSON.stringify(data, null, 2), "utf-8");
    this.cache.set(fingerprint, data);
  }

  load(chunkId: string): Chunk | null {
    const fingerprint = chunkId.split("-").slice(0, -1).join("-");
    const data = this.loadFile(fingerprint);
    return data?.chunks.find(c => c.id === chunkId) ?? null;
  }

  loadBatch(chunkIds: string[]): Chunk[] {
    const result: Chunk[] = [];
    for (const id of chunkIds) {
      const chunk = this.load(id);
      if (chunk) result.push(chunk);
    }
    return result;
  }

  loadByFingerprint(fingerprint: string): Chunk[] {
    return this.loadFile(fingerprint)?.chunks ?? [];
  }

  remove(fingerprint: string): void {
    const file = getChunkFile(fingerprint);
    if (fs.existsSync(file)) fs.unlinkSync(file);
    this.cache.delete(fingerprint);
  }

  exists(fingerprint: string): boolean {
    return fs.existsSync(getChunkFile(fingerprint));
  }
}

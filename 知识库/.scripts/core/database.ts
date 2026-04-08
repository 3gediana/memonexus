import * as fs from "fs";
import * as path from "path";
import Database from "better-sqlite3";

const DB_PATH = path.resolve(__dirname, "../../../.metadata/knowledge-base.db");

// 初始化数据库表
function initDB(db: Database.Database): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS files (
      fingerprint TEXT PRIMARY KEY,
      path TEXT NOT NULL,
      size INTEGER,
      mtime TEXT,
      status TEXT DEFAULT 'pending',
      indexed_at TEXT,
      chunks_count INTEGER
    )
  `);

  db.exec(`
    CREATE TABLE IF NOT EXISTS keyword_index (
      word TEXT NOT NULL,
      chunk_id TEXT NOT NULL,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY (word, chunk_id)
    )
  `);

  db.exec(`
    CREATE INDEX IF NOT EXISTS idx_keyword_chunk ON keyword_index(chunk_id)
  `);

  db.exec(`
    CREATE TABLE IF NOT EXISTS config (
      key TEXT PRIMARY KEY,
      value TEXT
    )
  `);
}

let globalDB: Database.Database | null = null;

export function getDB(): Database.Database {
  if (!globalDB) {
    const dir = path.dirname(DB_PATH);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });

    globalDB = new Database(DB_PATH);
    globalDB.pragma("journal_mode = WAL"); // 优化写入性能
    initDB(globalDB);
  }
  return globalDB;
}

// 文件记录操作
export interface FileRecord {
  fingerprint: string;
  path: string;
  size: number;
  mtime: string;
  status: string;
  indexedAt?: string;
  chunksCount?: number;
}

export class FileStore {
  private db: Database.Database;

  constructor() {
    this.db = getDB();
  }

  record(info: FileRecord): void {
    const stmt = this.db.prepare(`
      INSERT OR REPLACE INTO files (fingerprint, path, size, mtime, status, indexed_at, chunks_count)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `);
    stmt.run(
      info.fingerprint,
      info.path,
      info.size,
      info.mtime,
      info.status,
      info.indexedAt || null,
      info.chunksCount || null
    );
  }

  get(fingerprint: string): FileRecord | null {
    const stmt = this.db.prepare("SELECT * FROM files WHERE fingerprint = ?");
    const row = stmt.get(fingerprint) as any;
    if (!row) return null;
    return {
      fingerprint: row.fingerprint,
      path: row.path,
      size: row.size,
      mtime: row.mtime,
      status: row.status,
      indexedAt: row.indexed_at,
      chunksCount: row.chunks_count,
    };
  }

  getStatus(fingerprint: string): string {
    const stmt = this.db.prepare("SELECT status FROM files WHERE fingerprint = ?");
    const row = stmt.get(fingerprint) as any;
    return row?.status || "pending";
  }

  isIndexed(fingerprint: string): boolean {
    const stmt = this.db.prepare("SELECT status FROM files WHERE fingerprint = ?");
    const row = stmt.get(fingerprint) as any;
    return row?.status === "indexed";
  }

  getPendingFiles(): string[] {
    const stmt = this.db.prepare("SELECT path FROM files WHERE status = 'pending'");
    const rows = stmt.all() as any[];
    return rows.map(r => r.path);
  }

  getIndexedFiles(): FileRecord[] {
    const stmt = this.db.prepare("SELECT * FROM files WHERE status = 'indexed'");
    const rows = stmt.all() as any[];
    return rows.map(r => ({
      fingerprint: r.fingerprint,
      path: r.path,
      size: r.size,
      mtime: r.mtime,
      status: r.status,
      indexedAt: r.indexed_at,
      chunksCount: r.chunks_count,
    }));
  }

  remove(fingerprint: string): void {
    const stmt = this.db.prepare("DELETE FROM files WHERE fingerprint = ?");
    stmt.run(fingerprint);
  }

  // 关闭数据库连接
  close(): void {
    this.db.close();
    globalDB = null;
  }
}

// 关键词索引操作
export class KeywordStore {
  private db: Database.Database;

  constructor() {
    this.db = getDB();
  }

  add(word: string, chunkId: string): void {
    const stmt = this.db.prepare("INSERT OR IGNORE INTO keyword_index (word, chunk_id) VALUES (?, ?)");
    stmt.run(word, chunkId);
  }

  addBatch(entries: { word: string; chunkId: string }[]): void {
    const transaction = this.db.transaction((items: typeof entries) => {
      const stmt = this.db.prepare("INSERT OR IGNORE INTO keyword_index (word, chunk_id) VALUES (?, ?)");
      for (const item of items) {
        stmt.run(item.word, item.chunkId);
      }
    });
    transaction(entries);
  }

  search(word: string): string[] {
    const stmt = this.db.prepare("SELECT chunk_id FROM keyword_index WHERE word = ?");
    const rows = stmt.all(word) as any[];
    return rows.map(r => r.chunk_id);
  }

  remove(chunkId: string): void {
    const stmt = this.db.prepare("DELETE FROM keyword_index WHERE chunk_id = ?");
    stmt.run(chunkId);
  }

  // 批量搜索（用于多词查询）
  searchMany(words: string[]): Map<string, string[]> {
    const result = new Map<string, string[]>();
    for (const word of words) {
      result.set(word, this.search(word));
    }
    return result;
  }
}

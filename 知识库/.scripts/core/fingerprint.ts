import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";
import { FileStore, type FileRecord } from "./database";

export type FileStatus = "pending" | "indexing" | "indexed" | "error";

export interface FileFingerprint extends FileRecord {
  indexedAt?: string;
  chunksCount?: number;
}

export class FingerprintManager {
  private store: FileStore;

  constructor() {
    this.store = new FileStore();
  }

  compute(filePath: string): string {
    const content = fs.readFileSync(filePath);
    return crypto.createHash("md5").update(content).digest("hex").slice(0, 16);
  }

  getStatus(fingerprint: string): FileStatus {
    return this.store.getStatus(fingerprint) as FileStatus;
  }

  isIndexed(fingerprint: string): boolean {
    return this.store.isIndexed(fingerprint);
  }

  isModified(filePath: string): boolean {
    const current = this.compute(filePath);
    const entry = this.store.get(current);
    if (!entry) return true;
    return entry.fingerprint !== current;
  }

  record(info: FileFingerprint): void {
    this.store.record({
      fingerprint: info.fingerprint,
      path: info.path,
      size: info.size,
      mtime: info.mtime,
      status: info.status,
      indexedAt: info.indexedAt,
      chunksCount: info.chunksCount,
    });
  }

  getPendingFiles(): string[] {
    return this.store.getPendingFiles();
  }

  getIndexedFiles(): FileFingerprint[] {
    return this.store.getIndexedFiles();
  }

  removeRecord(fingerprint: string): void {
    this.store.remove(fingerprint);
  }

  // 关闭数据库
  close(): void {
    this.store.close();
  }
}

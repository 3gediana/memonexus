import * as fs from "fs";
import * as path from "path";
import { spawnSync } from "child_process";
import type { Chunk } from "./chunker";
import { KeywordStore } from "./database";

// 停用词表
const STOP_WORDS = new Set([
  "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
  "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会",
  "着", "没有", "看", "好", "自己", "这", "那", "但", "与", "及",
  "the", "a", "an", "is", "are", "was", "were", "be", "been",
  "have", "has", "had", "do", "does", "did", "will", "would",
  "could", "should", "may", "might", "of", "in", "on", "at",
  "to", "for", "with", "by", "from", "as", "or", "and", "not",
]);

// jieba 分词脚本路径
const JIEBA_SCRIPT = path.join(__dirname, "jieba-keyword.py");

export class KeywordIndexer {
  private store: KeywordStore;
  // 内存缓存，批量写入
  private buffer: { word: string; chunkId: string }[] = [];
  // jieba 可用性缓存
  private jiebaAvailable: boolean | null = null;

  constructor() {
    this.store = new KeywordStore();
    this.checkJieba();
  }

  /**
   * 检查 jieba 是否可用
   */
  private checkJieba(): void {
    if (!fs.existsSync(JIEBA_SCRIPT)) {
      this.jiebaAvailable = false;
      return;
    }
    const result = spawnSync("python", [JIEBA_SCRIPT, "测试"]);
    this.jiebaAvailable = result.status === 0;
    if (!this.jiebaAvailable) {
      console.warn("[KeywordIndexer] jieba 分词不可用，回退到 N-gram 方案");
    }
  }

  extract(text: string): string[] {
    const words = new Set<string>();

    // 英文词提取
    for (const w of text.toLowerCase().split(/[^a-z]+/)) {
      if (w.length >= 2 && w.length <= 20 && !STOP_WORDS.has(w)) words.add(w);
    }

    // 提取中文内容
    const cjkText = text.replace(/[^\u4e00-\u9fff]/g, " ");
    if (!cjkText.trim()) {
      return Array.from(words);
    }

    if (this.jiebaAvailable) {
      // 使用 jieba 分词
      const result = spawnSync("python", [JIEBA_SCRIPT, cjkText], {
        encoding: "utf-8",
        timeout: 5000,
      });
      if (result.status === 0) {
        try {
          const output = JSON.parse(result.stdout);
          if (output.success && output.keywords) {
            output.keywords.forEach((w: string) => {
              if (w.length > 1 && !STOP_WORDS.has(w.toLowerCase())) {
                words.add(w);
              }
            });
          }
        } catch (e) {
          // 解析失败，回退到 N-gram
          this.extractCjkNgram(cjkText, words);
        }
      } else {
        // 执行失败，回退到 N-gram
        this.extractCjkNgram(cjkText, words);
      }
    } else {
      // jieba 不可用，使用 N-gram
      this.extractCjkNgram(cjkText, words);
    }

    return Array.from(words);
  }

  /**
   * 中文 N-gram 提取（回退方案）
   */
  private extractCjkNgram(cjk: string, words: Set<string>): void {
    const segs = cjk.split(/\s+/).filter(Boolean);
    for (const seg of segs) {
      for (let n = 2; n <= 3; n++) {
        for (let i = 0; i <= seg.length - n; i++) {
          const w = seg.slice(i, i + n);
          if (!STOP_WORDS.has(w)) words.add(w);
        }
      }
    }
  }

  add(chunkId: string, text: string): void {
    const keywords = this.extract(text);
    for (const word of keywords) {
      this.buffer.push({ word, chunkId });
    }
  }

  addBatch(chunks: Chunk[]): void {
    for (const chunk of chunks) {
      const keywords = this.extract(chunk.text);
      for (const word of keywords) {
        this.buffer.push({ word, chunkId: chunk.id });
      }
    }
    this.flush();
  }

  search(query: string): string[] {
    const keywords = this.extract(query);
    if (keywords.length === 0) return [];

    // 每个词的命中集合
    const sets = keywords.map(word => {
      return new Set(this.store.search(word));
    });

    // TF 近似：按出现词数排序
    const scoreMap = new Map<string, number>();
    for (const set of sets) {
      for (const id of set) {
        scoreMap.set(id, (scoreMap.get(id) ?? 0) + 1);
      }
    }

    return Array.from(scoreMap.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([id]) => id);
  }

  remove(chunkId: string): void {
    this.store.remove(chunkId);
  }

  flush(): void {
    if (this.buffer.length === 0) return;
    this.store.addBatch(this.buffer);
    this.buffer = [];
  }
}

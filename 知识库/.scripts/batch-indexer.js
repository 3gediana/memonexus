/**
 * 批量索引入口 - 由 Python 调用
 * 用法: node batch-indexer.js <file1> [file2] [file3] ...
 * 输出: JSON
 */
const { FingerprintManager } = require("./dist/core/fingerprint");
const { Chunker } = require("./dist/core/chunker");
const { KeywordIndexer } = require("./dist/core/keyword-index");
const { VectorIndexer } = require("./dist/core/vector-index");
const { ContentStore } = require("./dist/core/content-store");
const { ReExtractor } = require("./dist/core/extractor");

const args = process.argv.slice(2);
if (args.length === 0) {
  console.log(JSON.stringify({ success: false, error: "No files provided" }));
  process.exit(0);
}

const filePaths = args;

async function main() {
  const fm = new FingerprintManager();
  const chunker = new Chunker();
  const kwIndexer = new KeywordIndexer();
  const vecIndexer = new VectorIndexer();
  const store = new ContentStore();
  const extractor = new ReExtractor(fm, chunker, kwIndexer, vecIndexer, store);

  try {
    await extractor.init();
  } catch (e) {
    // 向量模型加载失败不影响纯关键词索引
  }

  const results = [];
  for (const filePath of filePaths) {
    try {
      const result = await extractor.extractFile(filePath);
      results.push({ file: filePath, ...result });
    } catch (e) {
      results.push({ file: filePath, success: false, error: e.message });
    }
  }

  console.log(JSON.stringify({ success: true, results }));
}

main().catch(e => {
  console.log(JSON.stringify({ success: false, error: e.message }));
  process.exit(1);
});

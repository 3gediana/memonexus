const fs = require('fs');
const path = require('path');

const SCRIPTS_DIR = path.resolve(__dirname);
const MATERIAL_DIR = path.resolve(__dirname, '../资料');

// 扫描版 PDF（不索引）
const SCAN_PDF = 'machine-learning---zhou-zhihua.pdf';

// 文本类 PDF（重新索引）
const TEXT_PDFS = [
  'fundamentals-of-artificial-intelligence-general-education-course.pdf',
  'illustrated-large-model-generative-ai-principles-and-practical-applications.pdf',
  'introduction-to-deep-learning-theory-and-implementation-based-on-python-yasushi-saito-2.pdf',
];

async function main() {
  const { ReExtractor } = require('./dist/core/extractor');
  const { FingerprintManager } = require('./dist/core/fingerprint');
  const { Chunker } = require('./dist/core/chunker');
  const { KeywordIndexer } = require('./dist/core/keyword-index');
  const { VectorIndexer } = require('./dist/core/vector-index');
  const { ContentStore } = require('./dist/core/content-store');

  const fm = new FingerprintManager();
  const chunker = new Chunker();
  const kwIndexer = new KeywordIndexer();
  const vecIndexer = new VectorIndexer();
  const store = new ContentStore();

  const extractor = new ReExtractor(fm, chunker, kwIndexer, vecIndexer, store);
  await extractor.init();

  console.log('开始索引文本类 PDF...\n');

  for (const pdf of TEXT_PDFS) {
    const pdfPath = path.join(MATERIAL_DIR, pdf);
    if (!fs.existsSync(pdfPath)) {
      console.log('跳过 (不存在):', pdf);
      continue;
    }

    console.log('索引中:', pdf);
    const result = await extractor.extractFile(pdfPath);
    if (result.success) {
      console.log('  结果：' + result.chunksCount + ' 块\n');
    } else {
      console.log('  失败:', result.error, '\n');
    }
  }

  console.log('索引完成!');
  console.log('注：扫描版 PDF (' + SCAN_PDF + ') 未被索引');
}

main().catch(console.error);

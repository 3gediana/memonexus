import fs from "fs";
import path from "path";
import { createRequire } from "module";
const require = createRequire(import.meta.url);

// 测试 PDF
async function testPDF(filePath) {
  try {
    const { getDocument } = await import("./node_modules/pdfjs-dist/legacy/build/pdf.mjs");
    const cMapUrl = path.resolve("./node_modules/pdfjs-dist/cmaps/") + "/";
    const data = new Uint8Array(fs.readFileSync(filePath));
    const doc = await getDocument({ data, cMapUrl, cMapPacked: true }).promise;
    let text = "";
    for (let i = 1; i <= Math.min(3, doc.numPages); i++) {
      const page = await doc.getPage(i);
      const content = await page.getTextContent();
      text += content.items.map(item => item.str).join(" ");
    }
    console.log(`✅ PDF: 提取 ${text.length} 字符，前80字: ${text.slice(0, 80)}`);
  } catch (e) {
    console.error(`❌ PDF 失败: ${e.message}`);
  }
}

// 测试 Office 格式（docx/pptx/xlsx）
async function testOffice(filePath, ext) {
  try {
    const { parseOffice } = require("officeparser");
    const ast = await parseOffice(filePath);
    function extractFromAst(node) {
      if (!node) return "";
      if (typeof node === "string") return node;
      if (node.text) return node.text;
      if (Array.isArray(node)) return node.map(extractFromAst).join(" ");
      if (node.children) return extractFromAst(node.children);
      if (node.content) return extractFromAst(node.content);
      return "";
    }
    const text = extractFromAst(ast);
    console.log(`✅ ${ext.toUpperCase()}: 提取 ${text.length} 字符，前80字: ${text.slice(0, 80)}`);
  } catch (e) {
    console.error(`❌ ${ext.toUpperCase()} 失败: ${e.message}`);
  }
}

// 扫描测试目录
const testDir = "G:/知识库/资料";
const files = fs.readdirSync(testDir);

console.log("=== 开始测试文件提取 ===\n");

for (const file of files) {
  const filePath = path.join(testDir, file);
  const ext = path.extname(file).toLowerCase();
  console.log(`\n测试文件: ${file}`);
  if (ext === ".pdf") await testPDF(filePath);
  else if ([".docx", ".pptx", ".xlsx", ".xls", ".odt", ".odp", ".ods"].includes(ext))
    await testOffice(filePath, ext);
  else console.log(`⚠️  格式 ${ext} 暂不测试`);
}

console.log("\n=== 测试完成 ===");

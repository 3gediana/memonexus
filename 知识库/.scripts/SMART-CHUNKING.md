# 智能分块模块说明

## 功能概述

智能分块模块 (`chunker.ts`) 支持按文档结构、内容类型进行智能分块，确保结构化内容保持完整，同时保持语义连贯性。

## 分块优先级

```
1. 代码块（```code```）   → 保持完整，单独成块
2. 表格（Markdown）        → 保持完整，单独成块
3. 公式（LaTeX）          → 保持完整，单独成块
4. 标题层级（# 到 ######） → 识别并关联到后续内容
5. 段落边界（\n\n）       → 优先在段落处分块
6. 句子边界（。！.!?）     → 其次在句子处分块
```

## 配置选项

```typescript
interface ChunkOptions {
  // 基础配置
  chunkSize: number;           // 目标块大小（默认 1000 字符）
  minChunkSize: number;        // 最小块大小（默认 200 字符）
  maxChunkSize: number;        // 最大块大小（默认 2000 字符）
  overlap: number;             // 重叠字符数（默认 150 字符）

  // 内容类型感知
  detectCodeBlocks: boolean;   // 检测代码块（默认 true）
  detectTables: boolean;       // 检测表格（默认 true）
  detectFormulas: boolean;     // 检测公式（默认 true）
  detectHeadings: boolean;     // 检测标题层级（默认 true）

  // 边界处理
  respectBoundary: boolean;    // 尊重文本边界（默认 true）
  keepParagraphTogether: boolean;  // 保持段落完整（默认 true）
}
```

## 输出格式

每个分块包含以下元信息：

```typescript
interface Chunk {
  id: string;              // 唯一标识
  text: string;            // 块内容
  index: number;           // 块索引
  startPos: number;        // 起始位置
  endPos: number;          // 结束位置
  page?: number;           // 页码（如果有）
  keywords?: string[];     // 关键词
  vector?: number[];       // 向量嵌入

  // 智能分块元信息
  blockType?: 'code' | 'table' | 'formula' | 'heading' | 'paragraph' | 'mixed';
  headingLevel?: number;   // 标题层级（1-6）
  headingText?: string;    // 所属标题文本
}
```

## 使用示例

```typescript
import { Chunker } from './core/chunker';

const chunker = new Chunker({
  chunkSize: 1000,
  overlap: 150,
  detectCodeBlocks: true,
  detectTables: true,
  detectFormulas: true,
  detectHeadings: true,
});

const text = `# 机器学习基础

机器学习是人工智能的一个分支。

## 监督学习

监督学习需要标注数据。

\`\`\`python
def train():
    pass
\`\`\`

| 参数 | 说明 |
|------|------|
| lr   | 学习率 |

$$E = mc^2$$
`;

const chunks = chunker.split(text, 'doc-fingerprint');
console.log(`分成 ${chunks.length} 块`);

chunks.forEach(chunk => {
  console.log(`块 ${chunk.index}: 类型=${chunk.blockType}, 标题=${chunk.headingText}`);
});
```

## 分块效果示例

### 输入文本

```markdown
# 机器学习基础

机器学习是人工智能的一个分支。

## 监督学习

### 线性回归

线性回归公式：

$$y = wx + b$$

### 决策树

```python
def train(data):
    if all_same_class(data):
        return LeafNode(class=data[0].class)
```

## 无监督学习

### K-Means

| 参数 | 说明 |
|------|------|
| k    | 聚类数 |
```

### 输出分块

| 块 ID | 类型 | 标题层级 | 所属标题 | 说明 |
|-------|------|----------|----------|------|
| 1 | heading | 1 | - | # 机器学习基础 |
| 2 | paragraph | 1 | 机器学习基础 | 机器学习是人工智能的一个分支。 |
| 3 | heading | 2 | - | ## 监督学习 |
| 4 | paragraph | 2 | 监督学习 | 监督学习需要标注数据。 |
| 5 | heading | 3 | - | ### 线性回归 |
| 6 | paragraph | 3 | 线性回归 | 线性回归公式： |
| 7 | formula | 3 | 线性回归 | $$y = wx + b$$ |
| 8 | heading | 3 | - | ### 决策树 |
| 9 | paragraph | 3 | 决策树 | 决策树是一种算法。 |
| 10 | code | 3 | 决策树 | ```python...``` |
| 11 | heading | 2 | - | ## 无监督学习 |
| 12 | paragraph | 2 | 无监督学习 | 无监督学习不需要标注数据。 |
| 13 | heading | 3 | - | ### K-Means |
| 14 | table | 3 | K-Means | \|参数\|说明\| |

## 断点查找策略

当块大小超过 `chunkSize` 时，按以下优先级查找断点：

1. **段落边界** (`\n\n`) - 优先在段落分界处切断
2. **句子边界** (`. ! ? ! ？。；;`) - 其次在句子结束处切断
3. **空格边界** (` `) - 英文单词之间
4. **强制切断** - 没有合适边界时在 `chunkSize` 位置切断

## 重叠设计

相邻块之间有 `overlap` 字符的重叠区域，目的：

- 避免关键信息被切在两块边界上
- 向量搜索时，重叠部分帮助"跨块"匹配
- 保持上下文连贯性

示例（overlap=150）：
```
块 1: [...第 1 段末尾 150 字...]
块 2: [...第 1 段末尾 150 字...第 2 段开头...]
```

## 性能优化

- 使用正则表达式预扫描所有结构化内容
- 按优先级过滤重叠的结构块
- 一次遍历生成最终块列表

## 兼容性

- 保持与原有 `Chunk` 接口兼容
- 新增元信息字段均为可选
- 可通过配置关闭智能检测功能

## 相关文件

- `core/chunker.ts` - 智能分块模块
- `core/extractor.ts` - 文本提取模块
- `config.json` - 配置文件

/**
 * 智能分块模块
 * 支持按文档结构、内容类型、语义相似度进行分块
 *
 * 分块策略（优先级从高到低）：
 * 1. 代码块（```code```）- 保持完整
 * 2. 表格（Markdown/简单表格）- 保持完整
 * 3. 公式（LaTeX）- 保持完整
 * 4. 标题层级 - 按章节分块（核心策略）
 * 5. 自然段落 - 按空行分块
 * 6. 句子边界 - 其次在句子处分块
 *
 * 改进说明：
 * - 不再使用固定字符数（1000）切分
 * - 优先按章节/段落结构自然分块
 * - 仅当段落过长时才在句子边界切断
 */

export interface ChunkOptions {
  // 基础配置
  chunkSize: number;           // 目标块大小（字符数）
  minChunkSize: number;        // 最小块大小
  maxChunkSize: number;        // 最大块大小
  overlap: number;             // 重叠字符数

  // 内容类型感知
  detectCodeBlocks: boolean;   // 检测代码块
  detectTables: boolean;       // 检测表格
  detectFormulas: boolean;     // 检测公式
  detectHeadings: boolean;     // 检测标题层级

  // 边界处理
  respectBoundary: boolean;
  keepParagraphTogether: boolean;  // 尽量保持段落完整
}

export interface Chunk {
  id: string;
  text: string;
  index: number;
  startPos: number;
  endPos: number;
  page?: number;
  keywords?: string[];
  vector?: number[];

  // 新增：分块元信息
  blockType?: 'code' | 'table' | 'formula' | 'heading' | 'paragraph' | 'mixed';
  headingLevel?: number;       // 标题层级（1-6）
  headingText?: string;        // 所属标题文本
  confidence?: number;         // 分块置信度
}

const DEFAULTS: ChunkOptions = {
  chunkSize: 800,            // 改为 800，更适应段落长度
  minChunkSize: 100,
  maxChunkSize: 1500,        // 降低上限
  overlap: 100,              // 降低重叠
  detectCodeBlocks: true,
  detectTables: true,
  detectFormulas: true,
  detectHeadings: true,
  respectBoundary: true,
  keepParagraphTogether: true,
};

// 内容块结构
interface ContentBlock {
  type: 'code' | 'table' | 'formula' | 'heading' | 'text';
  start: number;
  end: number;
  content: string;
  level?: number;      // 标题层级
  metadata?: Record<string, any>;
}

export class Chunker {
  private opts: ChunkOptions;

  constructor(options?: Partial<ChunkOptions>) {
    this.opts = { ...DEFAULTS, ...options };
  }

  /**
   * 智能分块主入口
   */
  split(text: string, fingerprint: string): Chunk[] {
    // 1. 提取结构化内容块
    const blocks = this.extractStructuredBlocks(text);

    // 2. 对纯文本部分进行智能分块
    const chunks: Chunk[] = [];
    let idx = 1;
    let currentHeading: { level: number; title: string } = { level: 0, title: '' };

    for (const block of blocks) {
      if (block.type === 'heading') {
        // 更新当前标题
        currentHeading = { level: block.level || 0, title: block.metadata?.title || '' };
        chunks.push({
          id: `${fingerprint}-${idx.toString().padStart(3, "0")}`,
          text: block.content,
          index: idx,
          startPos: block.start,
          endPos: block.end,
          blockType: block.type,
          headingLevel: block.level,
        });
        idx++;
      } else if (block.type !== 'text') {
        // 结构化内容保持完整，继承当前标题
        chunks.push({
          id: `${fingerprint}-${idx.toString().padStart(3, "0")}`,
          text: block.content,
          index: idx,
          startPos: block.start,
          endPos: block.end,
          blockType: block.type,
          headingLevel: currentHeading.level,
          headingText: currentHeading.title,
        });
        idx++;
      } else {
        // 普通文本使用语义自适应分块
        const textChunks = this.splitBySemanticStructure(
          block.content,
          block.start,
          fingerprint,
          idx,
          currentHeading.level,
          currentHeading.title
        );
        chunks.push(...textChunks);
        idx += textChunks.length;
      }
    }

    return chunks;
  }

  /**
   * 提取结构化内容块（代码、表格、公式、标题）
   */
  private extractStructuredBlocks(text: string): ContentBlock[] {
    const blocks: ContentBlock[] = [];
    const len = text.length;
    let pos = 0;

    // 收集所有结构化块的起始位置
    const allMatches: Array<{block: ContentBlock; priority: number}> = [];

    // 查找所有代码块
    if (this.opts.detectCodeBlocks) {
      const codeRegex = /```(\w*)\n([\s\S]*?)```/g;
      let match;
      while ((match = codeRegex.exec(text)) !== null) {
        allMatches.push({
          priority: 1,
          block: {
            type: 'code',
            start: match.index,
            end: match.index + match[0].length,
            content: match[0],
            metadata: { language: match[1] || 'unknown' },
          }
        });
      }
    }

    // 查找所有表格
    if (this.opts.detectTables) {
      const tableRegex = /(\|[^\n]+\|\n)+\|[-:\s|]+\|(\n\|[^\n]+\|)*/g;
      let match;
      while ((match = tableRegex.exec(text)) !== null) {
        allMatches.push({
          priority: 2,
          block: {
            type: 'table',
            start: match.index,
            end: match.index + match[0].length,
            content: match[0],
          }
        });
      }
    }

    // 查找所有公式
    if (this.opts.detectFormulas) {
      // 行间公式 $$...$$
      const displayFormulaRegex = /\$\$([\s\S]*?)\$\$/g;
      let match;
      while ((match = displayFormulaRegex.exec(text)) !== null) {
        allMatches.push({
          priority: 3,
          block: {
            type: 'formula',
            start: match.index,
            end: match.index + match[0].length,
            content: match[0],
          }
        });
      }
    }

    // 查找所有标题
    if (this.opts.detectHeadings) {
      const headingRegex = /^(#{1,6})\s+(.+)$/gm;
      let match;
      while ((match = headingRegex.exec(text)) !== null) {
        allMatches.push({
          priority: 4,
          block: {
            type: 'heading',
            start: match.index,
            end: match.index + match[0].length,
            content: match[0],
            level: match[1].length,
            metadata: { title: match[2] },
          }
        });
      }
    }

    // 按起始位置排序
    allMatches.sort((a, b) => a.block.start - b.block.start);

    // 移除重叠的块（保留优先级高的）
    const filtered: typeof allMatches = [];
    let lastEnd = -1;

    for (const item of allMatches) {
      if (item.block.start >= lastEnd) {
        filtered.push(item);
        lastEnd = item.block.end;
      }
    }

    // 生成最终的块列表
    pos = 0;
    for (const item of filtered) {
      const block = item.block;

      // 添加之前的纯文本
      if (block.start > pos) {
        blocks.push({
          type: 'text',
          start: pos,
          end: block.start,
          content: text.slice(pos, block.start),
        });
      }

      blocks.push(block);
      pos = block.end;
    }

    // 添加剩余的纯文本
    if (pos < len) {
      blocks.push({
        type: 'text',
        start: pos,
        end: len,
        content: text.slice(pos),
      });
    }

    return blocks;
  }

  /**
   * 语义自适应分块（核心改进）
   *
   * 分块优先级：
   * 1. 按章节分块（有子标题时）
   * 2. 按自然段落分块（空行分隔）
   * 3. 按列表项分块
   * 4. 按句子边界分块（段落过长时）
   */
  private splitBySemanticStructure(
    text: string,
    offset: number,
    fingerprint: string,
    startIdx: number,
    headingLevel: number,
    headingText: string
  ): Chunk[] {
    const chunks: Chunk[] = [];
    let idx = startIdx;

    // 步骤 1: 按自然段落分割（空行分隔）
    const paragraphs = this.splitByParagraphs(text);

    let currentChunk: string[] = [];
    let currentLength = 0;

    for (const para of paragraphs) {
      const trimmed = para.trim();
      if (!trimmed) continue;

      const paraLength = trimmed.length;

      // 检查是否是列表项
      const isListItem = /^(\d+\.|[-*•])\s/.test(trimmed);

      // 如果当前累积长度 + 新段落 > maxChunkSize，先输出当前块
      if (currentLength + paraLength > this.opts.maxChunkSize && currentChunk.length > 0) {
        // 输出当前块
        chunks.push(this.createChunk(
          currentChunk.join('\n\n'),
          offset,
          fingerprint,
          idx++,
          headingLevel,
          headingText,
          'paragraph'
        ));
        currentChunk = [];
        currentLength = 0;
      }

      // 列表项特殊处理：尽量保持完整
      if (isListItem && paraLength > this.opts.chunkSize) {
        // 列表项过长，单独成块并可能分割
        if (currentChunk.length > 0) {
          chunks.push(this.createChunk(
            currentChunk.join('\n\n'),
            offset,
            fingerprint,
            idx++,
            headingLevel,
            headingText,
            'paragraph'
          ));
          currentChunk = [];
          currentLength = 0;
        }
        // 分割长列表项
        const subChunks = this.splitLongParagraph(para, offset, fingerprint, idx, headingLevel, headingText);
        chunks.push(...subChunks);
        idx += subChunks.length;
      } else {
        // 普通段落：添加到当前块
        currentChunk.push(trimmed);
        currentLength += paraLength;

        // 如果当前块足够大，输出
        if (currentLength >= this.opts.chunkSize) {
          chunks.push(this.createChunk(
            currentChunk.join('\n\n'),
            offset,
            fingerprint,
            idx++,
            headingLevel,
            headingText,
            'paragraph'
          ));
          currentChunk = [];
          currentLength = 0;
        }
      }
    }

    // 输出剩余的块
    if (currentChunk.length > 0) {
      chunks.push(this.createChunk(
        currentChunk.join('\n\n'),
        offset,
        fingerprint,
        idx,
        headingLevel,
        headingText,
        'paragraph'
      ));
    }

    return chunks;
  }

  /**
   * 按自然段落分割（空行分隔）
   */
  private splitByParagraphs(text: string): string[] {
    // 先按双换行分割段落
    const byDoubleNewline = text.split(/\n\s*\n/);
    const result: string[] = [];

    for (const para of byDoubleNewline) {
      const trimmed = para.trim();
      if (!trimmed) continue;

      // 如果段落太长（超过 maxChunkSize），进一步按单换行分割
      if (trimmed.length > this.opts.maxChunkSize) {
        const bySingleNewline = trimmed.split(/\n/);
        let currentChunk = '';

        for (const line of bySingleNewline) {
          if (currentChunk.length + line.length > this.opts.maxChunkSize && currentChunk) {
            result.push(currentChunk);
            currentChunk = line;
          } else {
            currentChunk += (currentChunk ? '\n' : '') + line;
          }
        }

        if (currentChunk) {
          result.push(currentChunk);
        }
      } else {
        result.push(trimmed);
      }
    }

    return result;
  }

  /**
   * 分割过长的段落
   */
  private splitLongParagraph(
    text: string,
    offset: number,
    fingerprint: string,
    startIdx: number,
    headingLevel: number,
    headingText: string
  ): Chunk[] {
    const chunks: Chunk[] = [];
    const maxLen = this.opts.maxChunkSize;

    if (text.length <= maxLen) {
      chunks.push(this.createChunk(text, offset, fingerprint, startIdx, headingLevel, headingText, 'paragraph'));
      return chunks;
    }

    // 按句子分割
    const sentences = this.splitBySentences(text);
    let currentChunk: string[] = [];
    let currentLength = 0;
    let idx = startIdx;

    for (const sent of sentences) {
      const sentLen = sent.length;
      if (currentLength + sentLen > maxLen && currentChunk.length > 0) {
        chunks.push(this.createChunk(
          currentChunk.join(''),
          offset,
          fingerprint,
          idx++,
          headingLevel,
          headingText,
          'mixed'
        ));
        currentChunk = [];
        currentLength = 0;
      }
      currentChunk.push(sent);
      currentLength += sentLen;
    }

    if (currentChunk.length > 0) {
      chunks.push(this.createChunk(
        currentChunk.join(''),
        offset,
        fingerprint,
        idx,
        headingLevel,
        headingText,
        'mixed'
      ));
    }

    return chunks;
  }

  /**
   * 按句子分割
   */
  private splitBySentences(text: string): string[] {
    // 匹配中英文句子结束符
    const sentenceRegex = /([.!?.!?。！？；；\n]+)/g;
    const parts = text.split(sentenceRegex);
    const sentences: string[] = [];

    for (let i = 0; i < parts.length; i += 2) {
      const sentence = parts[i] + (parts[i + 1] || '');
      if (sentence.trim()) {
        sentences.push(sentence);
      }
    }

    return sentences;
  }

  /**
   * 创建 Chunk 对象
   */
  private createChunk(
    text: string,
    offset: number,
    fingerprint: string,
    idx: number,
    headingLevel: number,
    headingText: string,
    blockType: string
  ): Chunk {
    const pos = offset; // 简化处理
    return {
      id: `${fingerprint}-${idx.toString().padStart(3, "0")}`,
      text,
      index: idx,
      startPos: pos,
      endPos: pos + text.length,
      blockType: blockType as any,
      headingLevel,
      headingText,
    };
  }

  /**
   * 智能分割纯文本（保留向后兼容）
   */
  private smartSplitText(
    text: string,
    offset: number,
    fingerprint: string,
    startIdx: number,
    headingLevel: number,
    headingText: string
  ): Chunk[] {
    return this.splitBySemanticStructure(
      text, offset, fingerprint, startIdx, headingLevel, headingText
    );
  }

  /**
   * 寻找最佳断点位置
   */
  private findBestBreakPoint(text: string, start: number, end: number): number {
    // 优先级 1: 段落边界
    const paraBreak = text.lastIndexOf('\n\n', end);
    if (paraBreak > start + 50) return paraBreak + 2;

    // 优先级 2: 句子边界
    const sentBreak = Math.max(
      text.lastIndexOf('。', end),
      text.lastIndexOf('！', end),
      text.lastIndexOf('？', end),
      text.lastIndexOf('.', end),
      text.lastIndexOf('!', end),
      text.lastIndexOf('?', end),
      text.lastIndexOf('\n', end),
      text.lastIndexOf('；', end),
      text.lastIndexOf(';', end),
    );
    if (sentBreak > start + 20) return sentBreak + 1;

    // 优先级 3: 空格边界（英文）
    const spaceBreak = text.lastIndexOf(' ', end);
    if (spaceBreak > start + 20) return spaceBreak;

    // 没有合适的边界，强制切断
    return end;
  }

  /**
   * 批量分块
   */
  splitBatch(texts: Map<string, string>): Map<string, Chunk[]> {
    const result = new Map<string, Chunk[]>();
    for (const [fingerprint, text] of texts) {
      result.set(fingerprint, this.split(text, fingerprint));
    }
    return result;
  }
}

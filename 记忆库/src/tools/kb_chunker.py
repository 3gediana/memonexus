"""知识库智能分块模块

对齐 Node.js 版 chunker.js 的核心逻辑，改进标题处理：
- 标题不单独成块，而是作为前缀附加到后续正文
- 代码块/表格/公式保持完整
- 段落按语义边界分割
- 最小块 100 字，避免碎片化
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    id: str
    text: str
    index: int
    start_pos: int
    end_pos: int
    block_type: str = "paragraph"
    heading_level: int = 0
    heading_text: str = ""


@dataclass
class StructuredBlock:
    type: str
    start: int
    end: int
    content: str
    level: int = 0
    metadata: dict = field(default_factory=dict)


CHUNK_SIZE = 800
MIN_CHUNK_SIZE = 100
MAX_CHUNK_SIZE = 1500
OVERLAP = 100

STOP_WORDS = {
    "的",
    "了",
    "在",
    "是",
    "我",
    "有",
    "和",
    "就",
    "不",
    "人",
    "都",
    "一",
    "一个",
    "上",
    "也",
    "很",
    "到",
    "说",
    "要",
    "去",
    "你",
    "会",
    "着",
    "没有",
    "看",
    "好",
    "自己",
    "这",
    "那",
    "但",
    "与",
    "及",
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "with",
    "by",
    "from",
    "as",
    "or",
    "and",
    "not",
}


def _extract_structured_blocks(text: str) -> list:
    """提取结构化内容块（代码、表格、公式、标题）"""
    blocks = []
    all_matches = []

    # 代码块
    for m in re.finditer(r"```(\w*)\n([\s\S]*?)```", text):
        all_matches.append(
            {
                "priority": 1,
                "block": StructuredBlock(
                    type="code",
                    start=m.start(),
                    end=m.end(),
                    content=m.group(0),
                    metadata={"language": m.group(1) or "unknown"},
                ),
            }
        )

    # 表格
    for m in re.finditer(r"(\|[^\n]+\|\n)+\|[-:\s|]+\|(\n\|[^\n]+\|)*", text):
        all_matches.append(
            {
                "priority": 2,
                "block": StructuredBlock(
                    type="table",
                    start=m.start(),
                    end=m.end(),
                    content=m.group(0),
                ),
            }
        )

    # 行间公式
    for m in re.finditer(r"\$\$([\s\S]*?)\$\$", text):
        all_matches.append(
            {
                "priority": 3,
                "block": StructuredBlock(
                    type="formula",
                    start=m.start(),
                    end=m.end(),
                    content=m.group(0),
                ),
            }
        )

    # 标题
    for m in re.finditer(r"^(#{1,6})\s+(.+)$", text, re.MULTILINE):
        all_matches.append(
            {
                "priority": 4,
                "block": StructuredBlock(
                    type="heading",
                    start=m.start(),
                    end=m.end(),
                    content=m.group(0),
                    level=len(m.group(1)),
                    metadata={"title": m.group(2)},
                ),
            }
        )

    all_matches.sort(key=lambda x: x["block"].start)

    # 去重叠，保留优先级高的
    filtered = []
    last_end = -1
    for item in all_matches:
        if item["block"].start >= last_end:
            filtered.append(item)
            last_end = item["block"].end

    # 生成最终块列表
    pos = 0
    for item in filtered:
        block = item["block"]
        if block.start > pos:
            blocks.append(
                StructuredBlock(
                    type="text",
                    start=pos,
                    end=block.start,
                    content=text[pos : block.start],
                )
            )
        blocks.append(block)
        pos = block.end

    if pos < len(text):
        blocks.append(
            StructuredBlock(
                type="text",
                start=pos,
                end=len(text),
                content=text[pos:],
            )
        )

    return blocks


def _split_by_paragraphs(text: str) -> list:
    """按自然段落分割（空行分隔）"""
    by_double = re.split(r"\n\s*\n", text)
    result = []
    for para in by_double:
        trimmed = para.strip()
        if not trimmed:
            continue
        if len(trimmed) > MAX_CHUNK_SIZE:
            by_single = trimmed.split("\n")
            current = ""
            for line in by_single:
                if len(current) + len(line) > MAX_CHUNK_SIZE and current:
                    result.append(current)
                    current = line
                else:
                    current += ("\n" if current else "") + line
            if current:
                result.append(current)
        else:
            result.append(trimmed)
    return result


def _split_by_sentences(text: str) -> list:
    """按句子边界分割"""
    parts = re.split(r"([.!?.!?。！？；；\n]+)", text)
    sentences = []
    for i in range(0, len(parts), 2):
        sentence = parts[i] + (parts[i + 1] if i + 1 < len(parts) else "")
        if sentence.strip():
            sentences.append(sentence)
    return sentences


def _find_best_break(text: str, start: int, end: int) -> int:
    """寻找最佳断点位置"""
    para_break = text.rfind("\n\n", start, end)
    if para_break > start + 50:
        return para_break + 2

    sent_break = max(
        text.rfind("。", start, end),
        text.rfind("！", start, end),
        text.rfind("？", start, end),
        text.rfind(".", start, end),
        text.rfind("!", start, end),
        text.rfind("?", start, end),
        text.rfind("\n", start, end),
        text.rfind("；", start, end),
        text.rfind(";", start, end),
    )
    if sent_break > start + 20:
        return sent_break + 1

    space_break = text.rfind(" ", start, end)
    if space_break > start + 20:
        return space_break

    return end


def split(text: str, fingerprint: str) -> list:
    """智能分块主入口

    Args:
        text: 完整文本
        fingerprint: 文件指纹

    Returns:
        Chunk 列表
    """
    blocks = _extract_structured_blocks(text)
    chunks = []
    idx = 1

    # 标题累积 buffer：标题不单独成块，附加到后续正文
    pending_headings = []

    for block in blocks:
        if block.type == "heading":
            # 累积标题，不立即输出
            pending_headings.append(block)

        elif block.type != "text":
            # 结构化内容（代码/表格/公式）保持完整
            heading_prefix = ""
            if pending_headings:
                heading_prefix = "\n".join(h.content for h in pending_headings) + "\n"
                pending_headings = []

            content = heading_prefix + block.content
            chunks.append(
                Chunk(
                    id=f"{fingerprint}-{idx:03d}",
                    text=content,
                    index=idx,
                    start_pos=block.start,
                    end_pos=block.end,
                    block_type=block.type,
                    heading_level=block.level,
                    heading_text=block.metadata.get("title", ""),
                )
            )
            idx += 1

        else:
            # 普通文本：先附加累积的标题前缀
            heading_prefix = ""
            current_heading_level = 0
            current_heading_text = ""
            if pending_headings:
                heading_prefix = "\n".join(h.content for h in pending_headings) + "\n"
                current_heading_level = pending_headings[-1].level
                current_heading_text = pending_headings[-1].metadata.get("title", "")
                pending_headings = []

            text_chunks = _split_text_content(
                block.content,
                block.start,
                fingerprint,
                idx,
                heading_prefix,
                current_heading_level,
                current_heading_text,
            )
            chunks.extend(text_chunks)
            idx += len(text_chunks)

    # 文件末尾剩余的标题（没有后续正文），合并到最后一个块或单独成块
    if pending_headings and chunks:
        # 附加到最后一个块
        heading_text = "\n".join(h.content for h in pending_headings)
        chunks[-1].text = heading_text + "\n" + chunks[-1].text
    elif pending_headings:
        # 整个文件只有标题
        for h in pending_headings:
            chunks.append(
                Chunk(
                    id=f"{fingerprint}-{idx:03d}",
                    text=h.content,
                    index=idx,
                    start_pos=h.start,
                    end_pos=h.end,
                    block_type="heading",
                    heading_level=h.level,
                    heading_text=h.metadata.get("title", ""),
                )
            )
            idx += 1

    # 后处理：合并过小的块
    chunks = _merge_small_chunks(chunks)

    return chunks


def _split_text_content(
    text: str,
    offset: int,
    fingerprint: str,
    start_idx: int,
    heading_prefix: str,
    heading_level: int,
    heading_text: str,
) -> list:
    """分割普通文本内容，标题前缀附加到每个块"""
    chunks = []
    paragraphs = _split_by_paragraphs(text)
    current_chunk = []
    current_length = 0
    idx = start_idx

    for para in paragraphs:
        trimmed = para.strip()
        if not trimmed:
            continue

        para_len = len(trimmed)
        is_list_item = re.match(r"^(\d+\.|[-*•])\s", trimmed)

        # 当前块 + 新段落 > MAX_CHUNK_SIZE，先输出
        if current_length + para_len > MAX_CHUNK_SIZE and current_chunk:
            chunk_text = heading_prefix + "\n\n".join(current_chunk)
            chunks.append(
                Chunk(
                    id=f"{fingerprint}-{idx:03d}",
                    text=chunk_text,
                    index=idx,
                    start_pos=offset,
                    end_pos=offset + len(chunk_text),
                    block_type="paragraph",
                    heading_level=heading_level,
                    heading_text=heading_text,
                )
            )
            idx += 1
            current_chunk = []
            current_length = 0

        # 列表项过长，单独分割
        if is_list_item and para_len > CHUNK_SIZE:
            if current_chunk:
                chunk_text = heading_prefix + "\n\n".join(current_chunk)
                chunks.append(
                    Chunk(
                        id=f"{fingerprint}-{idx:03d}",
                        text=chunk_text,
                        index=idx,
                        start_pos=offset,
                        end_pos=offset + len(chunk_text),
                        block_type="paragraph",
                        heading_level=heading_level,
                        heading_text=heading_text,
                    )
                )
                idx += 1
                current_chunk = []
                current_length = 0

            sub_chunks = _split_long_paragraph(
                trimmed,
                offset,
                fingerprint,
                idx,
                heading_prefix,
                heading_level,
                heading_text,
            )
            chunks.extend(sub_chunks)
            idx += len(sub_chunks)
        else:
            current_chunk.append(trimmed)
            current_length += para_len

            if current_length >= CHUNK_SIZE:
                chunk_text = heading_prefix + "\n\n".join(current_chunk)
                chunks.append(
                    Chunk(
                        id=f"{fingerprint}-{idx:03d}",
                        text=chunk_text,
                        index=idx,
                        start_pos=offset,
                        end_pos=offset + len(chunk_text),
                        block_type="paragraph",
                        heading_level=heading_level,
                        heading_text=heading_text,
                    )
                )
                idx += 1
                current_chunk = []
                current_length = 0

    # 输出剩余
    if current_chunk:
        chunk_text = heading_prefix + "\n\n".join(current_chunk)
        chunks.append(
            Chunk(
                id=f"{fingerprint}-{idx:03d}",
                text=chunk_text,
                index=idx,
                start_pos=offset,
                end_pos=offset + len(chunk_text),
                block_type="paragraph",
                heading_level=heading_level,
                heading_text=heading_text,
            )
        )

    return chunks


def _split_long_paragraph(
    text: str,
    offset: int,
    fingerprint: str,
    start_idx: int,
    heading_prefix: str,
    heading_level: int,
    heading_text: str,
) -> list:
    """分割过长的段落"""
    chunks = []
    if len(text) <= MAX_CHUNK_SIZE:
        chunk_text = heading_prefix + text
        chunks.append(
            Chunk(
                id=f"{fingerprint}-{start_idx:03d}",
                text=chunk_text,
                index=start_idx,
                start_pos=offset,
                end_pos=offset + len(chunk_text),
                block_type="mixed",
                heading_level=heading_level,
                heading_text=heading_text,
            )
        )
        return chunks

    sentences = _split_by_sentences(text)
    current = []
    current_len = 0
    idx = start_idx

    for sent in sentences:
        sent_len = len(sent)
        if current_len + sent_len > MAX_CHUNK_SIZE and current:
            chunk_text = heading_prefix + "".join(current)
            chunks.append(
                Chunk(
                    id=f"{fingerprint}-{idx:03d}",
                    text=chunk_text,
                    index=idx,
                    start_pos=offset,
                    end_pos=offset + len(chunk_text),
                    block_type="mixed",
                    heading_level=heading_level,
                    heading_text=heading_text,
                )
            )
            idx += 1
            current = []
            current_len = 0
        current.append(sent)
        current_len += sent_len

    if current:
        chunk_text = heading_prefix + "".join(current)
        chunks.append(
            Chunk(
                id=f"{fingerprint}-{idx:03d}",
                text=chunk_text,
                index=idx,
                start_pos=offset,
                end_pos=offset + len(chunk_text),
                block_type="mixed",
                heading_level=heading_level,
                heading_text=heading_text,
            )
        )

    return chunks


def _merge_small_chunks(chunks: list) -> list:
    """合并过小的相邻块"""
    if len(chunks) <= 1:
        return chunks

    merged = []
    for chunk in chunks:
        if len(chunk.text) < MIN_CHUNK_SIZE and merged:
            # 合并到前一个块
            prev = merged[-1]
            prev.text = prev.text + "\n" + chunk.text
            prev.end_pos = chunk.end_pos
        else:
            merged.append(chunk)

    return merged

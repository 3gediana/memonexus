"""知识库关键词索引模块

对齐 Node.js 版 keyword-index.js：
- 英文词提取（正则分割 + 停用词过滤）
- 中文 jieba 分词（直接 import，不用 spawn 子进程）
- N-gram 回退（jieba 不可用时）
- SQLite keyword_index 表存储
"""

import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

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

CUSTOM_DICT = [
    "深度学习",
    "机器学习",
    "神经网络",
    "反向传播",
    "卷积神经网络",
    "自然语言处理",
    "计算机视觉",
    "强化学习",
    "transformer",
    "注意力机制",
    "生成式 AI",
    "大语言模型",
    "嵌入向量",
    "语义检索",
    "知识图谱",
]

_jieba_loaded = False


def _ensure_jieba():
    """懒加载 jieba + 自定义词典"""
    global _jieba_loaded
    if _jieba_loaded:
        return True
    try:
        import jieba

        for word in CUSTOM_DICT:
            jieba.add_word(word)
        _jieba_loaded = True
        return True
    except ImportError:
        logger.warning("jieba 未安装，回退到 N-gram 方案")
        return False


def _extract_english(text: str) -> set:
    """提取英文关键词"""
    words = set()
    for w in re.split(r"[^a-zA-Z]+", text.lower()):
        if 2 <= len(w) <= 20 and w not in STOP_WORDS:
            words.add(w)
    return words


def _extract_chinese_jieba(text: str) -> set:
    """jieba 中文分词"""
    words = set()
    if not _ensure_jieba():
        return words
    import jieba

    for w in jieba.lcut(text):
        if len(w) > 1 and w not in STOP_WORDS:
            words.add(w)
    return words


def _extract_chinese_ngram(text: str) -> set:
    """中文 N-gram 回退方案"""
    words = set()
    segs = re.split(r"\s+", text)
    for seg in segs:
        for n in (2, 3):
            for i in range(len(seg) - n + 1):
                w = seg[i : i + n]
                if w not in STOP_WORDS:
                    words.add(w)
    return words


def extract_keywords(text: str) -> list:
    """提取关键词列表

    Args:
        text: 输入文本

    Returns:
        去重后的关键词列表
    """
    words = _extract_english(text)

    cjk_text = re.sub(r"[^\u4e00-\u9fff]", " ", text)
    if cjk_text.strip():
        if _ensure_jieba():
            words |= _extract_chinese_jieba(cjk_text)
        else:
            words |= _extract_chinese_ngram(cjk_text)

    return list(words)


class KeywordIndexer:
    """关键词索引器（SQLite 存储）"""

    def __init__(self, db):
        self.db = db
        self.buffer = []

    def add(self, chunk_id: str, text: str):
        """为单个 chunk 建立关键词索引"""
        keywords = extract_keywords(text)
        for word in keywords:
            self.buffer.append((word, chunk_id))

    def add_batch(self, chunks: list):
        """批量建立关键词索引

        Args:
            chunks: [{id, text}, ...]
        """
        for chunk in chunks:
            keywords = extract_keywords(chunk["text"])
            for word in keywords:
                self.buffer.append((word, chunk["id"]))
        self.flush()

    def search(self, query: str) -> list:
        """关键词搜索，返回按匹配词数排序的 chunk_id 列表"""
        keywords = extract_keywords(query)
        if not keywords:
            return []

        placeholders = ",".join("?" * len(keywords))
        rows = self.db.execute(
            f"SELECT word, chunk_id FROM keyword_index WHERE word IN ({placeholders})",
            keywords,
        ).fetchall()

        score_map = {}
        for word, chunk_id in rows:
            score_map[chunk_id] = score_map.get(chunk_id, 0) + 1

        return sorted(score_map.keys(), key=lambda x: score_map[x], reverse=True)

    def remove(self, chunk_id: str):
        """删除 chunk 的关键词索引"""
        self.db.execute("DELETE FROM keyword_index WHERE chunk_id = ?", (chunk_id,))

    def flush(self):
        """将缓存批量写入数据库"""
        if not self.buffer:
            return
        self.db.executemany(
            "INSERT OR IGNORE INTO keyword_index (word, chunk_id) VALUES (?, ?)",
            self.buffer,
        )
        self.db.commit()
        self.buffer = []

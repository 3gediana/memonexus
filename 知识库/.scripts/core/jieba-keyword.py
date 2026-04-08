#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中文关键词提取脚本（使用 jieba 分词）
用于知识库系统的关键词索引增强

依赖安装：
pip install jieba
"""

import sys
import json
import os

# 尝试导入 jieba
try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False
    print("警告：jieba 未安装", file=sys.stderr)

# 停用词表
STOP_WORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会",
    "着", "没有", "看", "好", "自己", "这", "那", "但", "与", "及",
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "of", "in", "on", "at",
    "to", "for", "with", "by", "from", "as", "or", "and", "not",
}

# 自定义专业词典（可根据需要扩展）
CUSTOM_DICT = [
    "深度学习", "机器学习", "神经网络", "反向传播", "卷积神经网络",
    "自然语言处理", "计算机视觉", "强化学习", "transformer", "注意力机制",
    "生成式 AI", "大语言模型", "嵌入向量", "语义检索", "知识图谱",
]


def load_custom_dict():
    """加载自定义词典"""
    if not JIEBA_AVAILABLE:
        return

    for word in CUSTOM_DICT:
        jieba.add_word(word)


def extract_keywords(text: str, top_k: int = None) -> list:
    """
    提取中文关键词

    Args:
        text: 输入文本
        top_k: 返回关键词数量上限（None 表示返回全部）

    Returns:
        关键词列表
    """
    if not JIEBA_AVAILABLE:
        return []

    # 精确模式分词
    words = jieba.lcut(text)

    # 过滤停用词和单字
    keywords = [w for w in words if len(w) > 1 and w not in STOP_WORDS]

    # 去重，保留顺序
    seen = set()
    unique_keywords = []
    for w in keywords:
        if w.lower() not in seen:
            seen.add(w.lower())
            unique_keywords.append(w)

    if top_k:
        return unique_keywords[:top_k]
    return unique_keywords


def main():
    """主函数"""
    load_custom_dict()

    # 从命令行参数或 stdin 读取文本
    if len(sys.argv) > 1:
        text = ' '.join(sys.argv[1:])
    else:
        text = sys.stdin.read()

    if not text.strip():
        print(json.dumps({"error": "输入文本为空"}, ensure_ascii=False))
        sys.exit(1)

    keywords = extract_keywords(text)

    result = {
        "success": True,
        "keywords": keywords,
        "count": len(keywords)
    }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

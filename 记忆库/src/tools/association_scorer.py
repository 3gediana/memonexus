"""
关联评分器 - 为候选记忆计算相关性分数
使用 BGE 向量模型计算语义相似度
"""

import math
import os
import numpy as np
import onnxruntime as ort
from datetime import datetime
from transformers import BertTokenizer
from src.tools.cluster_engine import get_cluster_engine


# BGE 模型路径（相对于项目根目录）
_MODEL_DIR = os.path.join(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ),
    "知识库",
    ".models",
    "bge-small-zh-v1.5",
)
_ONNX_PATH = os.path.join(_MODEL_DIR, "onnx", "model.onnx")
_TOKENIZER_PATH = _MODEL_DIR

# BGE 归一化指令前缀
_INSTRUCT = "为这个句子生成表示以用于检索相关文章："


class _EmbeddingModel:
    """BGE embedding 模型单例，懒加载"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def _init(self):
        if self._initialized:
            return
        try:
            self.tokenizer = BertTokenizer.from_pretrained(
                _TOKENIZER_PATH, local_files_only=True
            )
            self.session = ort.InferenceSession(
                _ONNX_PATH, providers=["CPUExecutionProvider"]
            )
            self.input_names = [i.name for i in self.session.get_inputs()]
            self._initialized = True
        except Exception:
            self._initialized = False

    def is_available(self) -> bool:
        self._init()
        return self._initialized

    def encode(self, texts: list[str]) -> np.ndarray:
        """批量编码文本为向量"""
        self._init()
        if not self._initialized:
            raise RuntimeError("Embedding model not available")

        # BGE 需要加指令前缀
        texts = [_INSTRUCT + t for t in texts]

        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="np",
        )

        feed = {
            "input_ids": encoded["input_ids"].astype(np.int64),
            "attention_mask": encoded["attention_mask"].astype(np.int64),
        }
        if "token_type_ids" in self.input_names:
            feed["token_type_ids"] = encoded["token_type_ids"].astype(np.int64)

        outputs = self.session.run(None, feed)[0]

        # BGE 使用 [CLS] token 的表示，并做 L2 归一化
        embeddings = outputs[:, 0]
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        embeddings = embeddings / norms

        return embeddings


def _cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """计算两个已归一化向量的余弦相似度"""
    return float(np.dot(vec_a, vec_b))


class AssociationScorer:
    """关联评分器"""

    def __init__(self):
        self.semantic_weight = 0.6
        self.time_weight = 0.4
        self._model = _EmbeddingModel()

    def calculate_score(self, main_memory: dict, candidate: dict) -> float:
        """
        计算候选记忆的相关性分数

        Args:
            main_memory: 主记忆 {"fingerprint", "memory", "tag", "created_at"}
            candidate: 候选记忆 {"fingerprint", "tag", "created_at"}

        Returns:
            相关性分数 (0-1)
        """
        semantic_score = self._semantic_similarity(main_memory, candidate)
        time_score = self._time_proximity(main_memory, candidate)

        # 聚类加分
        cluster_engine = get_cluster_engine()
        cluster_bonus = cluster_engine.get_cluster_score_bonus(
            main_memory.get("fingerprint"), candidate.get("fingerprint")
        )

        score = (
            semantic_score * self.semantic_weight
            + time_score * self.time_weight
            + cluster_bonus
        )
        return round(min(score, 1.0), 3)

    def _semantic_similarity(self, main: dict, candidate: dict) -> float:
        """计算语义相似度（BGE 向量余弦相似度）"""
        main_text = f"{main.get('memory', '')} {main.get('tag', '')}".strip()
        cand_text = f"{candidate.get('memory', '')} {candidate.get('tag', '')}".strip()

        if not main_text or not cand_text:
            return 0.0

        if not self._model.is_available():
            return self._keyword_fallback(main_text, cand_text)

        try:
            embeddings = self._model.encode([main_text, cand_text])
            return _cosine_similarity(embeddings[0], embeddings[1])
        except Exception:
            return self._keyword_fallback(main_text, cand_text)

    def compute_semantic_similarity(self, text_a: str, text_b: str) -> float:
        """直接计算两段文本的语义相似度（公开方法）"""
        if not text_a or not text_b:
            return 0.0

        if not self._model.is_available():
            return self._keyword_fallback(text_a, text_b)

        try:
            embeddings = self._model.encode([text_a, text_b])
            return _cosine_similarity(embeddings[0], embeddings[1])
        except Exception:
            return self._keyword_fallback(text_a, text_b)

    def _keyword_fallback(self, text_a: str, text_b: str) -> float:
        """模型不可用时的关键词重叠 fallback"""
        import jieba

        stopwords = {
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
        }
        words_a = {
            w for w in jieba.lcut(text_a.lower()) if len(w) > 1 and w not in stopwords
        }
        words_b = {
            w for w in jieba.lcut(text_b.lower()) if len(w) > 1 and w not in stopwords
        }
        if not words_a or not words_b:
            return 0.0
        return len(words_a & words_b) / len(words_a | words_b)

    def _time_proximity(self, main: dict, candidate: dict) -> float:
        """计算时间相邻度（高斯衰减）"""
        main_time = main.get("created_at")
        cand_time = candidate.get("created_at")

        if not main_time or not cand_time:
            return 0.5  # 无时间信息，给中等分

        try:
            main_dt = datetime.strptime(main_time[:10], "%Y-%m-%d")
            cand_dt = datetime.strptime(cand_time[:10], "%Y-%m-%d")
            days_diff = abs((main_dt - cand_dt).days)

            # 高斯衰减：7天半衰期
            sigma = 7.0
            score = math.exp(-(days_diff**2) / (2 * sigma**2))
            return score
        except Exception:
            return 0.5

    def score_candidates(self, main_memory: dict, candidates: list) -> list:
        """为候选列表打分并排序"""
        # 批量编码提升性能
        if self._model.is_available():
            scored = self._score_with_batch(main_memory, candidates)
        else:
            scored = self._score_one_by_one(main_memory, candidates)

        # 按分数降序排序
        scored.sort(key=lambda x: x["algo_score"], reverse=True)
        return scored

    def _score_with_batch(self, main_memory: dict, candidates: list) -> list:
        """使用批量编码的打分"""
        main_text = (
            f"{main_memory.get('memory', '')} {main_memory.get('tag', '')}".strip()
        )
        cand_texts = [c.get("tag", "").strip() for c in candidates]

        # 主记忆 + 所有候选一起编码
        all_texts = [main_text] + cand_texts
        try:
            embeddings = self._model.encode(all_texts)
            main_vec = embeddings[0]

            scored = []
            for i, candidate in enumerate(candidates):
                cand_vec = embeddings[i + 1]
                semantic_score = _cosine_similarity(main_vec, cand_vec)
                time_score = self._time_proximity(main_memory, candidate)

                cluster_engine = get_cluster_engine()
                cluster_bonus = cluster_engine.get_cluster_score_bonus(
                    main_memory.get("fingerprint"), candidate.get("fingerprint")
                )

                score = (
                    semantic_score * self.semantic_weight
                    + time_score * self.time_weight
                    + cluster_bonus
                )

                scored.append({**candidate, "algo_score": round(min(score, 1.0), 3)})

            return scored
        except Exception:
            return self._score_one_by_one(main_memory, candidates)

    def _score_one_by_one(self, main_memory: dict, candidates: list) -> list:
        """逐条打分（fallback）"""
        scored = []
        for candidate in candidates:
            score = self.calculate_score(main_memory, candidate)
            scored.append({**candidate, "algo_score": score})
        return scored


_scorer_instance = None


def get_scorer() -> AssociationScorer:
    """获取评分器实例（单例，避免重复加载 BGE 模型）"""
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = AssociationScorer()
    return _scorer_instance

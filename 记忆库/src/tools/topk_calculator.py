"""
动态topk计算器 - 根据多样性、长度、偏好调整召回数量
"""

from src.system.config import load_config
from src.tools.preference_tracker import get_preference_tracker


class TopkCalculator:
    """动态topk计算器"""

    def __init__(self):
        config = load_config()
        self.max_topk = config.get("max_memories_per_recall", 10)
        self.max_context = config.get("context_threshold", 150000)
        self.avg_memory_length = 100

    def calculate(
        self,
        base_topk: int,
        recall_blocks: list,
        context_length: int = 0,
        key: str = "",
    ) -> int:
        """
        计算动态topk

        Args:
            base_topk: 基础topk
            recall_blocks: 已召回的记忆块（用于多样性计算）
            context_length: 当前上下文长度
            key: 当前召回的key

        Returns:
            调整后的topk
        """
        diversity = self._diversity_factor(recall_blocks)
        length = self._length_factor(context_length, base_topk)

        # 使用用户偏好因子
        tracker = get_preference_tracker()
        preference = tracker.get_preference_factor(key)

        adjusted = round(base_topk * diversity * length * preference)
        return max(1, min(adjusted, self.max_topk))

    def _diversity_factor(self, recall_blocks: list) -> float:
        if len(recall_blocks) <= 1:
            return 1.5

        similarities = []
        for i in range(len(recall_blocks)):
            for j in range(i + 1, len(recall_blocks)):
                sim = self._block_similarity(recall_blocks[i], recall_blocks[j])
                similarities.append(sim)

        if not similarities:
            return 1.0

        avg_similarity = sum(similarities) / len(similarities)
        factor = 1.5 - avg_similarity
        return max(0.5, min(factor, 1.5))

    def _block_similarity(self, block1: dict, block2: dict) -> float:
        key_sim = 0.3 if block1.get("key") == block2.get("key") else 0.0

        words1 = set(block1.get("memory", "").lower().split())
        words2 = set(block2.get("memory", "").lower().split())

        if not words1 or not words2:
            return key_sim

        intersection = words1 & words2
        union = words1 | words2
        word_sim = len(intersection) / len(union) if union else 0.0

        return key_sim + word_sim * 0.7

    def _length_factor(self, context_length: int, base_topk: int) -> float:
        remaining = self.max_context - context_length
        if remaining <= 0:
            return 0.1

        max_possible = remaining // self.avg_memory_length
        if max_possible >= base_topk:
            return 1.0

        factor = max_possible / base_topk
        return max(0.1, factor)


_calculator_instance = None


def get_calculator() -> TopkCalculator:
    global _calculator_instance
    if _calculator_instance is None:
        _calculator_instance = TopkCalculator()
    return _calculator_instance

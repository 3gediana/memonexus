"""
用户偏好追踪器 - 统计各key的调用频率
"""

import json
import os
from src.system.config import get_current_instance_config


class PreferenceTracker:
    """用户偏好追踪器"""

    def __init__(self):
        self._history = None

    def get_history_file_path(self) -> str:
        """获取历史记录文件路径"""
        instance = get_current_instance_config()
        data_dir = os.path.dirname(instance["db_path"])
        return os.path.join(data_dir, "key_call_history.json")

    def _current_instance_key(self) -> str:
        from src.system.config import get_current_instance_config
        return get_current_instance_config()["db_path"]

    def load_history(self) -> dict:
        """加载调用历史"""
        # instance 变化了，清缓存
        cached = getattr(self, '_history_instance_key', None)
        current = self._current_instance_key()
        if cached is not None and cached != current:
            self._history = None

        if self._history is not None:
            return self._history

        history_file = self.get_history_file_path()
        if not os.path.exists(history_file):
            self._history = {}
            return self._history

        try:
            with open(history_file, "r", encoding="utf-8") as f:
                self._history = json.load(f)
            self._history_instance_key = current
            return self._history
        except:
            self._history = {}
            self._history_instance_key = current
            return self._history

    def save_history(self) -> dict:
        """保存调用历史"""
        try:
            history_file = self.get_history_file_path()
            os.makedirs(os.path.dirname(history_file), exist_ok=True)

            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(self._history or {}, f, ensure_ascii=False, indent=2)

            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def record_call(self, key: str):
        """记录一次key调用（带衰减机制）"""
        self.load_history()
        if self._history is None:
            self._history = {}
        # Apply decay: multiply all existing counts by 0.9
        for k in self._history:
            self._history[k] = self._history[k] * 0.9
        # Increment target key
        self._history[key] = self._history.get(key, 0) + 1
        self.save_history()

    def get_preference_factor(self, key: str) -> float:
        """
        获取指定key的偏好因子

        Returns:
            偏好因子 (0.5-1.5)
        """
        self.load_history()
        if not self._history:
            return 1.0

        total_calls = sum(self._history.values())
        if total_calls == 0:
            return 1.0

        key_calls = self._history.get(key, 0)
        call_ratio = key_calls / total_calls

        # 偏好因子：0.5-1.5
        factor = 0.5 + call_ratio
        return min(factor, 1.5)

    def get_all_preferences(self) -> dict:
        """获取所有key的偏好因子"""
        self.load_history()
        if not self._history:
            return {}

        total_calls = sum(self._history.values())
        if total_calls == 0:
            return {}

        preferences = {}
        for key, calls in self._history.items():
            call_ratio = calls / total_calls
            factor = 0.5 + call_ratio
            preferences[key] = min(factor, 1.5)

        return preferences

    def get_stats(self) -> dict:
        """获取统计信息"""
        self.load_history()
        if not self._history:
            return {"total_calls": 0, "keys": {}}

        total_calls = sum(self._history.values())
        return {
            "total_calls": total_calls,
            "keys": dict(
                sorted(self._history.items(), key=lambda x: x[1], reverse=True)
            ),
        }

    def clear_history(self) -> dict:
        """清空历史记录"""
        self._history = {}
        return self.save_history()


# 全局实例
_tracker_instance = None


def get_preference_tracker() -> PreferenceTracker:
    """获取偏好追踪器实例"""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = PreferenceTracker()
    return _tracker_instance

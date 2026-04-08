"""
召回命中计时器 - API层调度机制

当对话有记忆召回时，从模型输出后开始计时45s。
如果用户45s内没有回复，自动触发report_hits提交。
一小轮对话只触发一次。
"""

import threading
import time
from typing import Callable, Optional


class RecallHitTimer:
    """召回命中计时器"""

    def __init__(self, timeout_seconds: int = 45):
        self.timeout_seconds = timeout_seconds
        self._timer: Optional[threading.Timer] = None
        self._active = False
        self._callback: Optional[Callable] = None
        self._lock = threading.Lock()

    def set_callback(self, callback: Callable):
        """设置超时回调"""
        self._callback = callback

    def start_if_recalled(self, has_recalled: bool, pending_hits: list):
        """如果有记忆召回且有待上报命中，启动计时器"""
        if not has_recalled or not pending_hits:
            return

        with self._lock:
            # 如果计时器已激活，不重复启动
            if self._active:
                return
            self._cancel_timer()
            self._active = True
            self._pending_hits = pending_hits
            self._timer = threading.Timer(self.timeout_seconds, self._on_timeout)
            self._timer.daemon = True
            self._timer.start()

    def cancel(self):
        """用户回复时取消计时器"""
        with self._lock:
            self._cancel_timer()
            self._active = False

    def _cancel_timer(self):
        """内部取消计时器"""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _on_timeout(self):
        """超时回调"""
        with self._lock:
            if not self._active:
                return
            self._active = False
            hits = getattr(self, "_pending_hits", [])
            if hits and self._callback:
                try:
                    self._callback(hits)
                except Exception as e:
                    print(f"Recall timer callback error: {e}")

    def is_active(self) -> bool:
        """计时器是否激活"""
        with self._lock:
            return self._active


# 全局计时器实例
_global_timer = RecallHitTimer(timeout_seconds=45)


def get_recall_timer() -> RecallHitTimer:
    """获取全局计时器"""
    return _global_timer

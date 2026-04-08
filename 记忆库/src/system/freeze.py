import time
import threading
from src.system.config import load_config


class FreezeManager:
    def __init__(self, timeout_seconds: int = None):
        self._frozen = False
        self._freeze_time = None
        self._queue = []
        self._lock = threading.Lock()
        if timeout_seconds is None:
            config = load_config()
            self._timeout_seconds = config.get("freeze_timeout_seconds", 15)
        else:
            self._timeout_seconds = timeout_seconds

    def freeze(self) -> dict:
        with self._lock:
            self._frozen = True
            self._freeze_time = time.time()
            return {"success": True, "state": "frozen"}

    def unfreeze(self) -> dict:
        with self._lock:
            self._frozen = False
            self._freeze_time = None
            queue_messages = self._queue.copy()
            self._queue.clear()
            return {
                "success": True,
                "state": "active",
                "queue_messages": queue_messages,
            }

    def is_frozen(self) -> bool:
        with self._lock:
            return self._frozen

    def add_to_queue(self, message: str) -> dict:
        with self._lock:
            self._queue.append(message)
            return {"success": True, "queue_length": len(self._queue)}

    def get_queue(self) -> list:
        with self._lock:
            return self._queue.copy()

    def clear_queue(self) -> dict:
        with self._lock:
            self._queue.clear()
            return {"success": True, "queue_length": 0}

    def check_timeout(self) -> bool:
        with self._lock:
            if not self._frozen or self._freeze_time is None:
                return False
            elapsed = time.time() - self._freeze_time
            return elapsed >= self._timeout_seconds

    def get_status(self) -> dict:
        with self._lock:
            elapsed = None
            if self._frozen and self._freeze_time:
                elapsed = time.time() - self._freeze_time
            return {
                "state": "frozen" if self._frozen else "idle",
                "queue_length": len(self._queue),
                "queue_messages": self._queue.copy(),
                "timeout_seconds": self._timeout_seconds,
                "elapsed_seconds": elapsed,
                "timed_out": self.check_timeout() if self._frozen else False,
            }

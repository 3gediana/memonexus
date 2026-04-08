import threading
import time


class KeyLock:
    def __init__(self):
        self._locks = {}
        self._lock_for_locks = threading.Lock()

    def acquire(self, key: str, timeout: float = 5.0) -> bool:
        with self._lock_for_locks:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
        return self._locks[key].acquire(timeout=timeout)

    def release(self, key: str):
        with self._lock_for_locks:
            if key in self._locks:
                try:
                    self._locks[key].release()
                except RuntimeError:
                    pass

    def get_status(self) -> dict:
        with self._lock_for_locks:
            locked_keys = []
            for key, lock in self._locks.items():
                if lock.locked():
                    locked_keys.append(key)
            return {"total_keys": len(self._locks), "locked_keys": locked_keys}


class AssociationQueue:
    def __init__(self):
        self._queue = []
        self._lock = threading.Lock()

    def push(self, fingerprint: str):
        with self._lock:
            self._queue.append(fingerprint)

    def pop(self) -> str | None:
        with self._lock:
            if self._queue:
                return self._queue.pop(0)
            return None

    def is_empty(self) -> bool:
        with self._lock:
            return len(self._queue) == 0

    def size(self) -> int:
        with self._lock:
            return len(self._queue)

    def get_all(self) -> list:
        with self._lock:
            return self._queue.copy()

    def clear(self):
        with self._lock:
            self._queue.clear()


class ContextCommit:
    def __init__(self):
        self._pending = {}
        self._lock = threading.Lock()

    def stage(self, block_name: str, content: str):
        with self._lock:
            self._pending[block_name] = content

    def commit(self) -> dict:
        with self._lock:
            result = self._pending.copy()
            self._pending.clear()
            return result

    def clear(self):
        with self._lock:
            self._pending.clear()

    def get_pending(self) -> dict:
        with self._lock:
            return self._pending.copy()

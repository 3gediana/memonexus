import threading
from typing import Optional

class EventBroadcaster:
    """全局事件广播器 - 将 event_bus 事件广播给所有 SSE 监控客户端"""

    _instance: Optional['EventBroadcaster'] = None
    _lock = threading.Lock()

    def __init__(self):
        self._clients: list = []
        self._client_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> 'EventBroadcaster':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def register(self, queue) -> int:
        """注册一个 SSE 客户端队列，返回客户端ID"""
        with self._client_lock:
            self._clients.append(queue)
            return len(self._clients) - 1

    def unregister(self, queue) -> None:
        """注销一个 SSE 客户端队列"""
        with self._client_lock:
            if queue in self._clients:
                self._clients.remove(queue)

    def broadcast(self, event: dict) -> int:
        """广播事件给所有已注册的客户端，返回接收客户端数"""
        count = 0
        with self._client_lock:
            for client in self._clients:
                try:
                    client.put_nowait(event)
                    count += 1
                except:
                    pass
        return count

    @property
    def client_count(self) -> int:
        with self._client_lock:
            return len(self._clients)

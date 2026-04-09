"""AgentEventBus - Agent事件总线

用于在存储流程中发送事件到SSE流。
"""

import asyncio
from src.system.event_broadcaster import EventBroadcaster
from src.system.logger import get_module_logger

logger = get_module_logger("event_bus")


class AgentEventBus:
    """事件总线，用于在后台线程和主事件循环之间传递事件"""

    def __init__(self):
        self._queue = None
        self._loop = None
        self._heartbeat_task = None

    def bind_queue(self, queue: asyncio.Queue):
        """绑定事件队列"""
        self._queue = queue

    def bind_loop(self, loop):
        """绑定事件循环"""
        self._loop = loop

    def emit_thinking(self, agent: str, phase: str):
        """发送Agent思考事件"""
        if self._queue is None:
            return
        event = {
            "type": "agent_thinking",
            "agent": agent,
            "phase": phase,
        }
        self._queue.put_nowait(event)
        EventBroadcaster.get_instance().broadcast(event)
        logger.debug(f"[EventBus] emit_thinking: {agent} - {phase}")

    def emit_tool_call(self, agent: str, tool: str, params: dict):
        """发送Agent工具调用事件"""
        if self._queue is None:
            return
        event = {
            "type": "agent_tool_call",
            "agent": agent,
            "tool": tool,
            "params": params,
        }
        self._queue.put_nowait(event)
        EventBroadcaster.get_instance().broadcast(event)
        logger.debug(f"[EventBus] emit_tool_call: {agent} - {tool}")

    def emit_result(self, agent: str, result: dict):
        """发送Agent执行结果事件"""
        if self._queue is None:
            return
        event = {
            "type": "agent_result",
            "agent": agent,
            "result": result,
        }
        self._queue.put_nowait(event)
        EventBroadcaster.get_instance().broadcast(event)
        logger.debug(f"[EventBus] emit_result: {agent}")

    def emit_storage_progress(self, stage: str, progress: dict):
        """发送存储进度事件"""
        if self._queue is None:
            return
        event = {
            "type": "storage_progress",
            "stage": stage,
            "progress": progress,
        }
        self._queue.put_nowait(event)
        EventBroadcaster.get_instance().broadcast(event)
        logger.debug(f"[EventBus] emit_storage_progress: {stage}")

    async def _heartbeat_loop(self):
        """心跳循环，保持连接存活"""
        while True:
            try:
                await asyncio.sleep(15)
                if self._queue is not None:
                    self._queue.put_nowait({"type": "heartbeat"})
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[EventBus] heartbeat error: {e}")
                break

    def start_heartbeat(self):
        """启动心跳任务"""
        if self._loop is not None and self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    def stop_heartbeat(self):
        """停止心跳任务"""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

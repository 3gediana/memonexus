from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import asyncio
import contextlib
import json
import os
import sqlite3
import threading
from starlette.responses import StreamingResponse
import traceback

from src.system.logger import get_module_logger
from src.system.config import (
    create_instance,
    list_instances,
    load_config,
    save_config,
    switch_instance,
)
from src.db.init import init_database, init_sub_database
from src.system.main import handle_user_message, handle_user_message_streaming
from src.system.freeze import FreezeManager
from src.system.recall_timer import get_recall_timer
from src.system.event_bus import AgentEventBus
from src.system.event_broadcaster import EventBroadcaster
from src.tools.key_tools import create_key, get_key_overview, init_keys_directory
from src.tools.memory_tools import (
    add_memory_to_key,
    delete_memory_from_key,
    get_db,
    get_memory_by_fingerprint,
    list_memory_by_key,
    replace_memory_in_key,
)
from src.tools.edge_tools import create_edges, delete_edges, list_edges_by_fingerprint
from src.tools.query_tools import (
    get_cross_key_context,
    get_key_context,
    get_memory_by_fingerprint as get_memories_by_fingerprints,
)
from src.tools.sub_tools import insert_sub, list_sub, query_sub_by_time
from src.tools.kb_tools import execute_kb_tool
from src.tools.memory_space_tools import (
    add_memory as ms_add,
    remove_memory as ms_remove,
    update_memory as ms_update,
    list_memories as ms_list,
    init_memory_space,
)
from src.tools.cluster_engine import get_cluster_engine

app = FastAPI(title="Memory Assistant API", version="0.2.0")
logger = get_module_logger("api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

freeze_manager = FreezeManager()
dialogue_messages: list[dict] = []
dialogue_messages_lock = threading.Lock()
recall_timer = get_recall_timer()


def _on_recall_timeout(pending_hits: list):
    """计时器超时回调：提交命中统计"""
    from src.tools.edge_calibrator import get_calibrator
    from src.tools.memory_tools import get_db

    calibrator = get_calibrator()
    for fp in pending_hits:
        conn = get_db()
        try:
            edges = conn.execute(
                "SELECT from_fingerprint, to_fingerprint FROM edges WHERE from_fingerprint = ? OR to_fingerprint = ?",
                (fp, fp),
            ).fetchall()
        finally:
            conn.close()

        for edge in edges:
            calibrator.record_hit(edge["from_fingerprint"], edge["to_fingerprint"])


recall_timer.set_callback(_on_recall_timeout)


class ChatRequest(BaseModel):
    message: str
    turn: int = 1


class MemoryCreate(BaseModel):
    key: str
    content: str
    tag: str = ""
    summary_item: Optional[str] = None


class MemoryUpdate(BaseModel):
    key: str
    new_memory: str
    new_tag: str = ""
    new_summary_item: Optional[str] = None


class EdgeCreate(BaseModel):
    from_fp: str
    to_fp: str
    strength: float = 0.6
    reason: str = ""


class EdgeDelete(BaseModel):
    from_fp: str
    to_fp: str


class KeyCreate(BaseModel):
    name: str


class KbSearchRequest(BaseModel):
    query: str
    top_k: int = 5


class KbIndexRequest(BaseModel):
    paths: list[str]
    force_reindex: bool = False


class InstanceCreateRequest(BaseModel):
    name: str


class InstanceSwitchRequest(BaseModel):
    name: str


class ConfigUpdate(BaseModel):
    freeze_timeout_seconds: Optional[int] = None
    topk_default: Optional[int] = None
    context_threshold: Optional[int] = None
    idle_timeout: Optional[int] = None
    max_memories_per_recall: Optional[int] = None


def ok(data=None):
    return {"success": True, "data": data}


def fail(message: str, status_code: int = 400):
    raise HTTPException(status_code=status_code, detail=message)


def unwrap(result: dict, status_code: int = 400):
    if not result.get("success", False):
        error = result.get("error", "UNKNOWN_ERROR")
        if "NOT_FOUND" in error or "not found" in error.lower():
            fail(error, status_code=404)
        elif "UNAUTHORIZED" in error or "unauthorized" in error.lower():
            fail(error, status_code=401)
        elif "FORBIDDEN" in error or "forbidden" in error.lower():
            fail(error, status_code=403)
        else:
            fail(error, status_code=status_code)
    return result


def _get_memory_edges_with_details(fingerprint: str) -> list[dict]:
    edges_result = unwrap(list_edges_by_fingerprint(fingerprint), 404)
    edges = edges_result.get("edges", [])
    if not edges:
        return []

    related_fps = []
    for edge in edges:
        other_fp = (
            edge["to_fingerprint"]
            if edge["from_fingerprint"] == fingerprint
            else edge["from_fingerprint"]
        )
        related_fps.append(other_fp)

    related_lookup = {}
    related_result = get_memories_by_fingerprints(related_fps)
    if related_result.get("success"):
        for item in related_result.get("items", []):
            if item.get("found"):
                related_lookup[item["fingerprint"]] = item

    detailed_edges = []
    for edge in edges:
        other_fp = (
            edge["to_fingerprint"]
            if edge["from_fingerprint"] == fingerprint
            else edge["from_fingerprint"]
        )
        detailed_edges.append(
            {
                **edge,
                "other_fingerprint": other_fp,
                "other_memory": related_lookup.get(other_fp, {}),
            }
        )
    return detailed_edges


def _get_memory_edge_count_lookup() -> dict:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT fingerprint, COUNT(*) AS edge_count
        FROM (
            SELECT from_fingerprint AS fingerprint FROM edges
            UNION ALL
            SELECT to_fingerprint AS fingerprint FROM edges
        ) grouped
        GROUP BY fingerprint
        """
    ).fetchall()
    conn.close()
    return {row["fingerprint"]: row["edge_count"] for row in rows}


def _list_knowledge_documents() -> list[dict]:
    indexed = unwrap(execute_kb_tool("kb_list_indexed", {}))
    files = indexed.get("files", [])
    documents = []
    for item in files:
        fingerprint = item.get("fingerprint")
        if not fingerprint:
            continue
        doc_result = execute_kb_tool("kb_get_document", {"fingerprint": fingerprint})
        if not doc_result.get("success"):
            continue
        chunks = doc_result.get("chunks", [])
        preview = chunks[0].get("text", "")[:120] if chunks else ""
        documents.append(
            {
                "fingerprint": fingerprint,
                "name": item.get("name") or fingerprint,
                "path": item.get("path", ""),
                "size": item.get("size", 0),
                "chunk_count": doc_result.get("count", item.get("chunks_count", 0)),
                "preview": preview,
            }
        )
    return documents


@app.get("/api/instances")
async def get_instances():
    return ok(list_instances())


@app.get("/api/instances/current")
async def get_current_instance():
    info = list_instances()
    current_name = info["current_instance"]
    return ok({"name": current_name, **info["instances"][current_name]})


@app.post("/api/instances")
async def create_memory_instance(req: InstanceCreateRequest):
    result = create_instance(req.name)
    unwrap(result)
    init_database(result["instance"]["db_path"])
    init_sub_database(result["instance"]["sub_db_path"])
    init_keys_directory(result["instance"]["keys_dir"])
    return ok(result["instance"])


@app.post("/api/instances/use")
async def use_memory_instance(req: InstanceSwitchRequest):
    result = unwrap(switch_instance(req.name), 404)
    with dialogue_messages_lock:
        dialogue_messages.clear()
    return ok(result)


@app.get("/api/dialogue/messages")
async def get_dialogue_messages():
    with dialogue_messages_lock:
        return ok(dialogue_messages.copy())


@app.post("/api/dialogue/clear")
async def clear_dialogue_messages():
    """清空对话历史（开启新会话时调用）

    返回 SSE 流，实时推送存储事件：
    1. 取消45s静息计时器
    2. 解冻FreezeManager
    3. 流式处理 dialogue_messages 中的用户消息
    4. 清空对话上下文
    """
    recall_timer.cancel()
    freeze_manager.unfreeze()
    freeze_manager.clear_queue()

    # 提取待处理的用户消息
    messages_to_process = []
    with dialogue_messages_lock:
        messages_to_process = [
            entry["user_message"]
            for entry in dialogue_messages
            if entry.get("user_message")
        ]

    async def clear_event_generator():
        import time as time_module

        if not messages_to_process:
            with dialogue_messages_lock:
                dialogue_messages.clear()
            yield f"event: done\ndata: {json.dumps({'type': 'done', 'processed': 0})}\n\n"
            return

        yield f"event: clearing_start\ndata: {json.dumps({'type': 'clearing_start', 'total': len(messages_to_process)})}\n\n"

        q: asyncio.Queue = asyncio.Queue()
        event_bus = AgentEventBus()
        event_bus.bind_queue(q)
        event_bus.bind_loop(asyncio.get_running_loop())
        total_added = []

        def run_storage():
            from src.system.storage_flow import process_user_message

            for idx, msg in enumerate(messages_to_process):
                result = process_user_message(msg, idx + 1, event_bus=event_bus)
                if result.get("success") and result.get("memories_added"):
                    total_added.extend(result["memories_added"])
            q.put_nowait(None)

        t = threading.Thread(target=run_storage, daemon=True)
        t.start()

        # 流式推送事件
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=5)
            except asyncio.TimeoutError:
                continue

            if event is None:
                break

            event_type = event.get("type", "")
            if event_type == "agent_thinking":
                yield f"event: agent_thinking\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            elif event_type == "agent_tool_call":
                yield f"event: agent_tool_call\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            elif event_type == "agent_result":
                yield f"event: agent_result\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

        # 存储完成
        if total_added:
            transformed = [
                {
                    "memory_id": m.get("fingerprint", ""),
                    "key": m.get("key", ""),
                    "content_preview": m.get("memory", "")[:100]
                    + ("..." if len(m.get("memory", "")) > 100 else ""),
                }
                for m in total_added
            ]
            yield f"event: storage_result\ndata: {json.dumps({'type': 'storage_result', 'memories_added': transformed, 'total_memories': len(transformed)}, ensure_ascii=False)}\n\n"

        with dialogue_messages_lock:
            dialogue_messages.clear()

        logger.info(
            f"[clear] 存储 {len(messages_to_process)} 条用户消息, 新增 {len(total_added)} 条记忆"
        )
        yield f"event: done\ndata: {json.dumps({'type': 'done', 'processed': len(messages_to_process), 'memories_added': len(total_added)})}\n\n"

    return StreamingResponse(
        clear_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# @app.post("/api/chat")
# async def chat(req: ChatRequest):
#     return await send_dialogue(req)


@app.post("/api/chat/stream/{instance_id}")
async def chat_stream(instance_id: str, req: ChatRequest):
    """SSE流式对话端点"""
    logger.info(f"[SSE] 收到对话请求: {req.message[:50]}..., instance={instance_id}")

    # 切换到指定实例
    if instance_id:
        from src.system.config import switch_instance

        result = switch_instance(instance_id)
        if not result.get("success"):

            async def error_gen():
                yield f"data: {json.dumps({'type': 'error', 'message': f'instance not found: {instance_id}'})}\n\n"

            return StreamingResponse(error_gen(), media_type="text/event-stream")

    # 取消计时器并进入冻结态（积累消息，等unfreeze时批量存储）
    recall_timer.cancel()
    freeze_manager.freeze()

    async def event_generator():
        import threading
        import time

        final_content = ""
        final_has_recalled = False
        turn = req.turn
        q: asyncio.Queue = asyncio.Queue()
        last_heartbeat = time.time()
        stream_timeout = 120  # 120秒无数据视为超时

        event_bus = AgentEventBus()
        event_bus.bind_queue(q)
        event_bus.bind_loop(asyncio.get_running_loop())
        event_bus.start_heartbeat()

        def thread_worker():
            try:
                count = 0
                with dialogue_messages_lock:
                    dialogue_snapshot = dialogue_messages.copy()
                for event in handle_user_message_streaming(
                    req.message, req.turn, dialogue_snapshot, event_bus=event_bus
                ):
                    count += 1
                    q.put_nowait(event)
                logger.info(f"[SSE] thread_worker finished, total {count} events")
                q.put_nowait(None)
            except Exception as e:
                logger.error(f"[SSE] thread error: {e}")
                logger.error(traceback.format_exc())
                q.put_nowait({"type": "error", "message": str(e)})
                q.put_nowait(None)

        t = threading.Thread(target=thread_worker, daemon=True)
        t.start()

        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                except asyncio.TimeoutError:
                    elapsed = time.time() - last_heartbeat
                    if elapsed >= 15:
                        logger.info(f"[SSE] heartbeat ping, elapsed={elapsed:.1f}s")
                        yield f": heartbeat\n\n"
                        last_heartbeat = time.time()
                    continue

                if event is None:
                    logger.info("[SSE] got None, exiting loop")
                    break
                event_type = event.get("type", "content")
                last_heartbeat = time.time()
                logger.info(
                    f"[SSE] yielding event: {event_type}, content_len={len(event.get('delta', event.get('content', '')))}"
                )
                if event_type == "reasoning":
                    yield f"event: reasoning\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "content":
                    yield f"event: content\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "tool_call":
                    yield f"event: tool_call\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "tool_return":
                    yield f"event: tool_return\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "done":
                    final_content = event.get("content", "")
                    final_has_recalled = event.get("has_recalled", False)
                    yield f"event: done\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "error":
                    yield f"event: error\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "storage_result":
                    yield f"event: storage_result\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "agent_thinking":
                    yield f"event: agent_thinking\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "agent_tool_call":
                    yield f"event: agent_tool_call\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "agent_result":
                    yield f"event: agent_result\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "storage_progress":
                    yield f"event: storage_progress\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                elif event_type == "heartbeat":
                    yield f": heartbeat\n\n"
        except asyncio.CancelledError:
            logger.info("[SSE] Client disconnected, cleaning up...")
        finally:
            try:
                # ========== 流结束：解冻 + 45s计时器 + 存储 ==========
                logger.info("[SSE] running cleanup (unfreeze + heartbeat stop)")
                event_bus.stop_heartbeat()

                # 检查冻结是否超时（45s静息后自动触发report_hits）
                if freeze_manager.check_timeout():
                    logger.info("[SSE] freeze timed out, triggering report_hits")
                    from src.tools.edge_calibrator import get_calibrator
                    from src.tools.memory_tools import get_db

                    calibrator = get_calibrator()
                    # 对所有边记录hit（简化版：扫描最近创建的边）
                    conn = get_db()
                    try:
                        recent_edges = conn.execute(
                            "SELECT from_fingerprint, to_fingerprint FROM edges ORDER BY created_at DESC LIMIT 100"
                        ).fetchall()
                        for edge in recent_edges:
                            calibrator.record_hit(
                                edge["from_fingerprint"], edge["to_fingerprint"]
                            )
                    finally:
                        conn.close()
                    # 冻结超时视为新会话开始，解冻并清空队列（不存储中间态）
                    freeze_manager.unfreeze()
                    freeze_manager.clear_queue()
                else:
                    # 正常解冻，取出队列中积累的消息并存储
                    unfreeze_result = freeze_manager.unfreeze()
                    queue_messages = unfreeze_result.get("queue_messages", [])
                    if queue_messages:
                        try:
                            from src.system.storage_flow import process_user_message

                            total_added = []
                            for idx, msg in enumerate(queue_messages):
                                result = process_user_message(
                                    msg, idx + 1, event_bus=event_bus
                                )
                                if result.get("success") and result.get("memories_added"):
                                    total_added.extend(result["memories_added"])
                            if total_added:
                                import time as time_module

                                start_time = time_module.time()
                                transformed = []
                                for m in total_added:
                                    memory = m.get("memory", "")
                                    transformed.append(
                                        {
                                            "memory_id": m.get("fingerprint", ""),
                                            "key": m.get("key", ""),
                                            "content_preview": memory[:100]
                                            + ("..." if len(memory) > 100 else ""),
                                        }
                                    )
                                duration_ms = int((time_module.time() - start_time) * 1000)
                                yield f"event: storage_result\ndata: {json.dumps({'type': 'storage_result', 'memories_added': transformed, 'total_memories': len(transformed), 'duration_ms': duration_ms}, ensure_ascii=False)}\n\n"
                            logger.info(
                                f"[SSE] stored {len(queue_messages)} queued messages"
                            )
                        except Exception as e:
                            logger.error(f"[SSE] queued storage failed: {e}")

                # 保存对话到数据库
                if final_content:
                    from src.system.config import get_current_instance_config

                    instance_cfg = get_current_instance_config()
                    db_path = instance_cfg.get("db_path")
                    if db_path:
                        try:
                            conn = sqlite3.connect(db_path)
                            cur = conn.cursor()
                            cur.execute("""
                                CREATE TABLE IF NOT EXISTS dialogue_history (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    user_message TEXT NOT NULL,
                                    assistant_message TEXT NOT NULL,
                                    turn INTEGER NOT NULL,
                                    created_at TEXT NOT NULL
                                )
                            """)
                            cur.execute(
                                "INSERT INTO dialogue_history (user_message, assistant_message, turn, created_at) VALUES (?, ?, ?, ?)",
                                (
                                    req.message,
                                    final_content,
                                    turn,
                                    __import__("datetime").datetime.now().isoformat(),
                                ),
                            )
                            conn.commit()
                            conn.close()
                            logger.info(f"[SSE] dialogue saved: turn={turn}")
                        except Exception as e:
                            logger.error(f"[SSE] dialogue save failed: {e}")

                # 流结束后追加到 dialogue_messages（保持上下文）
                if final_content:
                    response_message = {
                        "turn": turn,
                        "user_message": req.message,
                        "assistant_message": final_content,
                        "has_recalled": final_has_recalled,
                    }
                    dialogue_messages.append(response_message)
                    logger.info(f"[SSE] dialogue appended to memory: turn={turn}")

                if final_has_recalled:
                    recall_timer.start_if_recalled(True, [])
                    logger.info("[SSE] 45s recall timer started")
            except Exception as e:
                logger.error(f"[SSE] cleanup error: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/memory/keys")
async def memory_keys():
    overview = unwrap(get_key_overview(include_summary=True))
    return ok(overview.get("keys", []))


@app.get("/api/memory/list")
async def memory_list(key: str = Query(...)):
    result = unwrap(list_memory_by_key(key), 404)
    edge_counts = _get_memory_edge_count_lookup()
    memories = []
    for memory in result.get("memories", []):
        memories.append(
            {**memory, "edges_count": edge_counts.get(memory["fingerprint"], 0)}
        )
    return ok(memories)


@app.post("/api/memory")
async def add_memory(mem: MemoryCreate):
    result = unwrap(
        add_memory_to_key(
            mem.key,
            mem.content,
            mem.tag,
            mem.summary_item or mem.content[:50],
        )
    )
    return ok(result)


@app.get("/api/memory/stats")
async def get_memory_stats():
    """Get comprehensive memory statistics"""
    try:
        conn = get_db()
        total = conn.execute("SELECT COUNT(*) as count FROM memory").fetchone()["count"]
        key_stats = conn.execute(
            "SELECT key, COUNT(*) as count FROM memory GROUP BY key ORDER BY count DESC"
        ).fetchall()
        recall_dist = conn.execute("""
            SELECT
                CASE
                    WHEN recall_count = 0 THEN '0'
                    WHEN recall_count <= 5 THEN '1-5'
                    WHEN recall_count <= 10 THEN '6-10'
                    ELSE '10+'
                END as bucket, COUNT(*) as count
            FROM memory GROUP BY bucket
        """).fetchall()
        value_dist = conn.execute("""
            SELECT
                CASE
                    WHEN value_score < 0.2 THEN '0-0.2'
                    WHEN value_score < 0.4 THEN '0.2-0.4'
                    WHEN value_score < 0.6 THEN '0.4-0.6'
                    WHEN value_score < 0.8 THEN '0.6-0.8'
                    ELSE '0.8-1.0'
                END as bucket, COUNT(*) as count
            FROM memory GROUP BY bucket
        """).fetchall()
        recent = conn.execute(
            "SELECT COUNT(*) as count FROM memory WHERE created_at >= datetime('now', '-7 days')"
        ).fetchone()["count"]
        top_recalled = conn.execute("""
            SELECT fingerprint, key, tag, recall_count, value_score, updated_at
            FROM memory ORDER BY value_score DESC LIMIT 5
        """).fetchall()

        # 周对比数据：上周（7-14天前）创建的记忆数和边数
        last_week_memories = conn.execute("""
            SELECT COUNT(*) as count FROM memory
            WHERE created_at >= datetime('now', '-14 days')
              AND created_at < datetime('now', '-7 days')
        """).fetchone()["count"]
        last_week_edges = conn.execute("""
            SELECT COUNT(*) as count FROM edges
            WHERE created_at >= datetime('now', '-14 days')
              AND created_at < datetime('now', '-7 days')
        """).fetchone()["count"]

        # 最近30天召回次数时间序列（按天聚合）
        recall_timeline = conn.execute("""
            SELECT
                DATE(created_at) as date,
                SUM(recall_count) as total_recalls
            FROM memory
            WHERE created_at >= datetime('now', '-30 days')
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """).fetchall()

        result = {
            "total": total,
            "by_key": {row["key"]: row["count"] for row in key_stats},
            "recall_distribution": {row["bucket"]: row["count"] for row in recall_dist},
            "value_distribution": {row["bucket"]: row["count"] for row in value_dist},
            "recent_7days": recent,
            "semantic_status": {"valid": total},
            "top_recalled": [
                {
                    "fingerprint": row["fingerprint"],
                    "key": row["key"],
                    "tag": row["tag"],
                    "recall_count": row["recall_count"],
                    "value_score": row["value_score"],
                    "last_recall_at": row["updated_at"],
                }
                for row in top_recalled
            ],
            "week_comparison": {
                "memories_last_week": last_week_memories,
                "edges_last_week": last_week_edges,
            },
            "recall_timeline": [
                {"date": row["date"], "recalls": row["total_recalls"]}
                for row in recall_timeline
            ],
        }
    except Exception as e:
        # Instance may not have database yet, return empty stats
        result = {
            "total": 0,
            "by_key": {},
            "recall_distribution": {},
            "value_distribution": {},
            "recent_7days": 0,
            "semantic_status": {"valid": 0},
            "top_recalled": [],
            "week_comparison": {"memories_last_week": 0, "edges_last_week": 0},
        }
    finally:
        conn.close()
    return ok(result)


@app.get("/api/memory/graph/nodes")
async def memory_graph_nodes(
    limit: int = Query(0, ge=0, description="返回条数，0表示返回全部"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    conn = get_db()
    try:
        total_count = conn.execute("SELECT COUNT(*) as count FROM memory").fetchone()[
            "count"
        ]
        if limit > 0:
            rows = conn.execute(
                "SELECT fingerprint, key, memory, tag, created_at, visibility, value_score, recall_count FROM memory ORDER BY visibility DESC, value_score DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT fingerprint, key, memory, tag, created_at, visibility, value_score, recall_count FROM memory ORDER BY visibility DESC, value_score DESC"
            ).fetchall()
    finally:
        conn.close()
    edge_counts = _get_memory_edge_count_lookup()

    engine = get_cluster_engine()
    louvain_clusters = engine._fingerprint_to_cluster or {}

    nodes = [
        {
            "id": row["fingerprint"],
            "fingerprint": row["fingerprint"],
            "key": row["key"],
            "tag": row["tag"],
            "memory": row["memory"],
            "created_at": row["created_at"],
            "weight": row["value_score"],
            "visibility": row["visibility"] if "visibility" in row.keys() else 1.0,
            "value_score": row["value_score"] if "value_score" in row.keys() else 0.5,
            "recall_count": row["recall_count"] if "recall_count" in row.keys() else 0,
            "edge_count": edge_counts.get(row["fingerprint"], 0),
            "cluster_id": louvain_clusters.get(row["fingerprint"]) or "unclustered",
        }
        for row in rows
    ]
    return ok({"nodes": nodes, "total": total_count, "limit": limit, "offset": offset})


@app.get("/api/memory/graph/edges")
async def memory_graph_edges():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT from_fingerprint, to_fingerprint, strength, effective_strength, reason, created_at FROM edges"
        ).fetchall()
    finally:
        conn.close()
    edges = [
        {
            "source": row["from_fingerprint"],
            "target": row["to_fingerprint"],
            "strength": row["strength"],
            "effective_strength": row["effective_strength"],
            "reason": row["reason"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return ok(edges)


@app.put("/api/memory/{old_fp}")
async def replace_memory(old_fp: str, update: MemoryUpdate):
    result = unwrap(
        replace_memory_in_key(
            update.key,
            old_fp,
            update.new_memory,
            update.new_tag,
            update.new_summary_item or update.new_memory[:50],
        )
    )
    return ok(result)


@app.get("/api/memory/clusters")
async def get_louvain_clusters():
    """获取Louvain聚类结果 - fingerprint到cluster_id的映射"""
    engine = get_cluster_engine()
    clusters = engine.load_clusters()
    fp_to_cluster = engine._fingerprint_to_cluster
    return ok(
        {
            "clusters": clusters,
            "fingerprint_to_cluster": fp_to_cluster,
        }
    )


@app.post("/api/memory/clusters/run")
async def run_clustering_api():
    """触发聚类重新计算"""
    engine = get_cluster_engine()
    result = engine.run_clustering()
    if result.get("success"):
        return ok(result)
    else:
        return fail(result.get("error", "聚类失败"))


@app.delete("/api/memory/{fingerprint}")
async def delete_memory(fingerprint: str, key: str = Query(...)):
    result = unwrap(delete_memory_from_key(key, fingerprint), 404)
    return ok(result)


@app.get("/api/memory/{fingerprint}")
async def get_memory_detail(fingerprint: str):
    memory_result = unwrap(get_memory_by_fingerprint(fingerprint), 404)
    memory = memory_result["memory"]
    edges = _get_memory_edges_with_details(fingerprint)
    return ok({**memory, "edges": edges, "edges_count": len(edges)})


@app.get("/api/memory/{fingerprint}/edges")
async def get_memory_edges(fingerprint: str):
    return ok(_get_memory_edges_with_details(fingerprint))


@app.post("/api/edges")
async def create_memory_edges(edge: EdgeCreate):
    result = unwrap(
        create_edges(
            [
                {
                    "from_fingerprint": edge.from_fp,
                    "to_fingerprint": edge.to_fp,
                    "strength": edge.strength,
                    "reason": edge.reason,
                }
            ]
        )
    )
    return ok(result)


@app.delete("/api/edges")
async def delete_memory_edges(edge: EdgeDelete):
    result = unwrap(
        delete_edges([{"from_fingerprint": edge.from_fp, "to_fingerprint": edge.to_fp}])
    )
    return ok(result)


@app.get("/api/edges/{fingerprint}")
async def list_edges(fingerprint: str):
    return ok(_get_memory_edges_with_details(fingerprint))


@app.post("/api/keys")
async def create_memory_key(key: KeyCreate):
    result = unwrap(create_key(key.name))
    return ok(result)


@app.get("/api/keys/list")
async def list_keys():
    overview = unwrap(get_key_overview(include_summary=False))
    return ok(overview.get("keys", []))


@app.get("/api/keys/overview")
async def keys_overview():
    overview = unwrap(get_key_overview(include_summary=True))
    return ok(overview.get("keys", []))


@app.post("/api/query/fingerprints")
async def query_by_fingerprints(fps: list[str]):
    result = unwrap(get_memories_by_fingerprints(fps))
    return ok(result.get("items", []))


@app.get("/api/query/context/{key}")
async def query_key_context(key: str):
    result = unwrap(get_key_context(key), 404)
    return ok(result)


@app.get("/api/query/cross-context/{fingerprint}")
async def cross_key_context(fingerprint: str):
    result = unwrap(get_cross_key_context(fingerprint), 404)
    return ok(result)


@app.post("/api/sub")
async def create_sub(sub: dict):
    result = unwrap(insert_sub(sub.get("message", ""), int(sub.get("turn", 1))))
    return ok(result)


@app.get("/api/sub/list")
async def list_subs(limit: int = 50, offset: int = 0):
    result = unwrap(list_sub(limit=limit, offset=offset))
    return ok({"items": result.get("items", []), "total": len(result.get("items", []))})


@app.get("/api/sub/query")
async def query_sub_range(start: str, end: str):
    result = unwrap(query_sub_by_time(start, end))
    return ok(result.get("items", []))


@app.get("/api/sub/{sub_id}/memories")
async def sub_memories(sub_id: int):
    conn = get_db()
    sub_conn = sqlite3.connect(
        load_config()["instances"][load_config()["current_instance"]]["sub_db_path"]
    )
    sub_conn.row_factory = sqlite3.Row
    sub_row = sub_conn.execute("SELECT * FROM sub WHERE id = ?", (sub_id,)).fetchone()
    if not sub_row:
        sub_conn.close()
        conn.close()
        fail("SUB_NOT_FOUND", 404)

    turn_index = sub_row["turn_index"]
    rows = conn.execute(
        "SELECT fingerprint, key, memory, tag, created_at FROM memory WHERE created_at >= ? ORDER BY created_at DESC",
        (sub_row["created_at"],),
    ).fetchall()
    sub_conn.close()
    conn.close()
    memories = [dict(row) for row in rows[:20]]
    return ok({"sub_id": sub_id, "turn_index": turn_index, "items": memories})


@app.post("/api/knowledge/search")
async def knowledge_search(req: KbSearchRequest):
    result = unwrap(
        execute_kb_tool("kb_search", {"query": req.query, "topK": req.top_k})
    )
    return ok(result)


@app.get("/api/knowledge/files")
async def knowledge_files():
    return ok(_list_knowledge_documents())


@app.get("/api/knowledge/{fingerprint}/chunks")
async def knowledge_chunks(fingerprint: str, offset: int = 0, limit: int = 16):
    result = unwrap(
        execute_kb_tool("kb_get_document", {"fingerprint": fingerprint}), 404
    )
    chunks = result.get("chunks", [])
    normalized = []
    for chunk in chunks[offset : offset + limit]:
        text = chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
        index = chunk.get("index") if isinstance(chunk, dict) else None
        chunk_id = (
            chunk.get("id")
            if isinstance(chunk, dict)
            else f"{fingerprint}-{index or 0}"
        )
        normalized.append(
            {
                "chunk_id": chunk_id,
                "index": index,
                "preview": text[:160],
                "text": text,
            }
        )
    return ok({"items": normalized, "total": len(chunks)})


@app.get("/api/knowledge/chunk/{chunk_id}")
async def knowledge_chunk(chunk_id: str):
    result = unwrap(execute_kb_tool("kb_get_chunk", {"chunkId": chunk_id}), 404)
    return ok(result)


@app.post("/api/kb/search")
async def search_kb(req: KbSearchRequest):
    return await knowledge_search(req)


@app.post("/api/kb/sans-search")
async def sans_search(req: KbSearchRequest):
    result = unwrap(
        execute_kb_tool(
            "kb_sans_search",
            {
                "query": req.query,
                "summaryInstruction": f"请总结与‘{req.query}’相关的知识",
                "topK": req.top_k,
            },
        )
    )
    return ok(result)


@app.post("/api/kb/index")
async def index_files(req: KbIndexRequest):
    result = unwrap(
        execute_kb_tool(
            "kb_index", {"paths": req.paths, "force_reindex": req.force_reindex}
        )
    )
    return ok(result)


@app.post("/api/kb/update-index")
async def update_index():
    result = unwrap(execute_kb_tool("kb_update_index", {}))
    return ok(result)


@app.get("/api/kb/chunk/{chunkId}")
async def get_chunk(chunkId: str):
    return await knowledge_chunk(chunkId)


@app.get("/api/kb/document/{fingerprint}")
async def get_document(fingerprint: str):
    result = unwrap(
        execute_kb_tool("kb_get_document", {"fingerprint": fingerprint}), 404
    )
    return ok(result)


@app.get("/api/kb/indexed")
async def list_indexed():
    return ok(_list_knowledge_documents())


@app.get("/api/kb/stats")
async def get_kb_stats():
    result = unwrap(execute_kb_tool("kb_get_stats", {}))
    return ok(result)


@app.delete("/api/kb/{fingerprint}")
async def remove_file(fingerprint: str):
    result = unwrap(execute_kb_tool("kb_remove_file", {"fingerprint": fingerprint}))
    return ok(result)


@app.get("/api/memory-space")
async def get_memory_space():
    result = ms_list()
    if not result.get("success"):
        return fail(result.get("error", "Failed to get memory space"), 500)
    return ok(result.get("items", []))


@app.post("/api/memory-space")
async def add_memory_space(content: str = Query(...), source: str = Query("user")):
    init_memory_space()
    result = ms_add(content, source)
    if not result.get("success"):
        return fail(result.get("error", "Failed to add memory space"), 500)
    return ok(result)


@app.put("/api/memory-space/{item_id}")
async def update_memory_space(item_id: int, content: str = Query(...)):
    result = ms_update(item_id, content)
    if not result.get("success"):
        return fail(result.get("error", "Failed to update memory space"), 500)
    return ok(result)


@app.delete("/api/memory-space/{item_id}")
async def remove_memory_space(item_id: int):
    result = ms_remove(item_id)
    if not result.get("success"):
        return fail(result.get("error", "Failed to remove memory space"), 500)
    return ok(result)


@app.get("/api/freeze/status")
async def get_freeze_status():
    return ok(freeze_manager.get_status())


@app.post("/api/freeze")
async def freeze():
    return ok(freeze_manager.freeze())


@app.post("/api/unfreeze")
async def unfreeze():
    return ok(freeze_manager.unfreeze())


@app.delete("/api/freeze/queue")
async def clear_freeze_queue():
    return ok(freeze_manager.clear_queue())


@app.get("/api/config")
async def get_config():
    config = load_config()
    return ok(
        {
            "freeze_timeout_seconds": config.get("freeze_timeout_seconds"),
            "topk_default": config.get("topk_default"),
            "context_threshold": config.get("context_threshold"),
            "idle_timeout": config.get("idle_timeout"),
            "max_memories_per_recall": config.get("max_memories_per_recall"),
        }
    )


@app.get("/api/monitor/status")
async def monitor_status():
    from src.tools.monitor import get_monitor

    monitor = get_monitor()
    report = monitor.get_full_report()
    return ok(report)


@app.get("/api/monitor/memory")
async def monitor_memory():
    from src.tools.monitor import get_monitor

    monitor = get_monitor()
    stats = monitor.get_memory_stats()
    return ok(stats)


@app.get("/api/monitor/edge")
async def monitor_edge():
    from src.tools.monitor import get_monitor

    monitor = get_monitor()
    stats = monitor.get_edge_stats()
    return ok(stats)


@app.post("/api/config")
async def set_config(update: ConfigUpdate):
    cfg = load_config()
    if update.freeze_timeout_seconds is not None:
        cfg["freeze_timeout_seconds"] = update.freeze_timeout_seconds
    if update.topk_default is not None:
        cfg["topk_default"] = update.topk_default
    if update.context_threshold is not None:
        cfg["context_threshold"] = update.context_threshold
    if update.idle_timeout is not None:
        cfg["idle_timeout"] = update.idle_timeout
    if update.max_memories_per_recall is not None:
        cfg["max_memories_per_recall"] = update.max_memories_per_recall
    save_config(cfg)
    return ok(cfg)


@app.post("/api/config/reset")
async def reset_config():
    default = {
        "freeze_timeout_seconds": 20,
        "topk_default": 2,
        "context_threshold": 150000,
        "idle_timeout": 30,
        "max_memories_per_recall": 10,
    }
    cfg = load_config()
    cfg.update(default)
    save_config(cfg)
    return ok(default)


@app.get("/api/monitor/stream")
async def monitor_stream():
    """Agent 协作事件流监控端点 - SSE 实时推送"""
    import asyncio
    import time
    import json

    async def event_generator():
        q: asyncio.Queue = asyncio.Queue()
        broadcaster = EventBroadcaster.get_instance()
        client_id = broadcaster.register(q)
        heartbeat_count = 0

        try:
            # 发送初始连接事件
            yield f"event: connected\ndata: {json.dumps({'type': 'connected', 'client_id': client_id})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15)
                    if event is None:
                        break
                    yield f"event: {event.get('type', 'message')}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # 发送心跳保持连接
                    heartbeat_count += 1
                    yield f": heartbeat {heartbeat_count}\n\n"

        finally:
            try:
                broadcaster.unregister(q)
            except Exception as e:
                logger.error(f"[monitor_stream] unregister error: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/value/top/{key}")
async def get_top_memories_by_key(key: str, limit: int = 10):
    """Get top memories by value score for a specific key"""
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT fingerprint, key, memory, tag, weight, value_score, recall_count, created_at
            FROM memory
            WHERE key = ?
            ORDER BY weight DESC, value_score DESC
            LIMIT ?
            """,
            (key, limit),
        ).fetchall()
    finally:
        conn.close()

    memories = [
        {
            "fingerprint": row["fingerprint"],
            "key": row["key"],
            "memory": row["memory"],
            "tag": row["tag"],
            "weight": row["weight"],
            "value_score": row["value_score"],
            "recall_count": row["recall_count"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return ok(memories)


@app.get("/api/value/top")
async def get_top_memories(limit: int = 10):
    """Get top memories by value score across all keys"""
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT fingerprint, key, memory, tag, weight, value_score, recall_count, created_at
            FROM memory
            ORDER BY weight DESC, value_score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    memories = [
        {
            "fingerprint": row["fingerprint"],
            "key": row["key"],
            "memory": row["memory"],
            "tag": row["tag"],
            "weight": row["weight"],
            "value_score": row["value_score"],
            "recall_count": row["recall_count"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return ok(memories)


@app.get("/api/edges/top")
async def get_top_edges(limit: int = 10):
    """Get top edges by strength"""
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT from_fingerprint, to_fingerprint, strength, effective_strength,
                   hit_count, recall_count, reason, created_at
            FROM edges
            ORDER BY effective_strength DESC, strength DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    edges = [
        {
            "source": row["from_fingerprint"],
            "target": row["to_fingerprint"],
            "strength": row["strength"],
            "effective_strength": row["effective_strength"],
            "hit_count": row["hit_count"],
            "recall_count": row["recall_count"],
            "reason": row["reason"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return ok(edges)


@app.get("/api/edge/stats")
async def get_edge_stats():
    try:
        conn = get_db()
        total = conn.execute("SELECT COUNT(*) as count FROM edges").fetchone()["count"]
        strength_dist = conn.execute("""
            SELECT
                CASE
                    WHEN strength < 0.3 THEN '0-0.3'
                    WHEN strength < 0.6 THEN '0.3-0.6'
                    WHEN strength < 0.9 THEN '0.6-0.9'
                    ELSE '0.9+'
                END as bucket,
                COUNT(*) as count
            FROM edges
            GROUP BY bucket
        """).fetchall()
        eff_strength_dist = conn.execute("""
            SELECT
                CASE
                    WHEN effective_strength < 0.3 THEN '0-0.3'
                    WHEN effective_strength < 0.6 THEN '0.3-0.6'
                    WHEN effective_strength < 0.9 THEN '0.6-0.9'
                    ELSE '0.9+'
                END as bucket,
                COUNT(*) as count
            FROM edges
            GROUP BY bucket
        """).fetchall()
        avg_strength = (
            conn.execute("SELECT AVG(strength) as avg FROM edges").fetchone()["avg"]
            or 0
        )
        avg_eff_strength = (
            conn.execute("SELECT AVG(effective_strength) as avg FROM edges").fetchone()[
                "avg"
            ]
            or 0
        )
        top_hits = conn.execute("""
            SELECT from_fingerprint, to_fingerprint, strength, effective_strength,
                   hit_count, recall_count, reason
            FROM edges
            ORDER BY hit_count DESC
            LIMIT 10
        """).fetchall()
        top_recalls = conn.execute("""
            SELECT from_fingerprint, to_fingerprint, strength, effective_strength,
                   hit_count, recall_count, reason
            FROM edges
            ORDER BY recall_count DESC
            LIMIT 10
        """).fetchall()

        cluster_stats = get_cluster_engine().get_stats()
    except Exception as e:
        # Instance may not have database yet
        conn = None
        total = 0
        strength_dist = []
        eff_strength_dist = []
        avg_strength = 0
        avg_eff_strength = 0
        top_hits = []
        top_recalls = []
        cluster_stats = {"cluster_count": 0}
    finally:
        if conn:
            conn.close()
    return ok(
        {
            "total": total,
            "strength_distribution": {
                row["bucket"]: row["count"] for row in strength_dist
            }
            if strength_dist
            else {},
            "effective_strength_distribution": {
                row["bucket"]: row["count"] for row in eff_strength_dist
            }
            if eff_strength_dist
            else {},
            "avg_strength": round(avg_strength, 3),
            "avg_effective_strength": round(avg_eff_strength, 3),
            "clusters_count": cluster_stats.get("cluster_count", 0),
            "top_by_hits": [
                {
                    "source": row["from_fingerprint"],
                    "target": row["to_fingerprint"],
                    "strength": row["strength"],
                    "effective_strength": row["effective_strength"],
                    "hit_count": row["hit_count"],
                    "recall_count": row["recall_count"],
                    "reason": row["reason"],
                }
                for row in top_hits
            ],
            "top_by_recalls": [
                {
                    "source": row["from_fingerprint"],
                    "target": row["to_fingerprint"],
                    "strength": row["strength"],
                    "effective_strength": row["effective_strength"],
                    "hit_count": row["hit_count"],
                    "recall_count": row["recall_count"],
                    "reason": row["reason"],
                }
                for row in top_recalls
            ],
        }
    )


@app.on_event("startup")
async def startup_event():
    """服务启动时执行数据库迁移"""
    logger.info("[Startup] Running database migrations...")
    from src.db.migrate import migrate_db

    result = migrate_db()
    if result.get("success"):
        logger.info("[Startup] Database migrations completed")
    else:
        logger.warning(f"[Startup] Some migrations failed: {result}")

    logger.info("[Startup] Initializing databases...")
    init_database()
    init_sub_database()
    init_memory_space()
    init_keys_directory()
    logger.info("[Startup] Initialization complete")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

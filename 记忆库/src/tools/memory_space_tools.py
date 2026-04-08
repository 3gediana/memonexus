"""记忆空间工具

用户主动维护的永久便签，始终出现在每轮对话上下文中。
支持用户手动管理 + 模型调用工具增删改查。
"""

import json
import sqlite3
import os
from datetime import datetime
from src.system.config import load_config, get_current_instance_config
from src.system.logger import get_module_logger

logger = get_module_logger("memory_space")


def _get_db_path() -> str:
    instance = get_current_instance_config()
    return instance["db_path"]


def _get_db() -> sqlite3.Connection:
    db_path = _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_memory_space(db_path: str = None) -> dict:
    """初始化记忆空间表"""
    try:
        if db_path is None:
            db_path = _get_db_path()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = _get_db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_space (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT DEFAULT 'user'
            )
        """)
        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def add_memory(content: str, source: str = "user") -> dict:
    """新增记忆空间条目"""
    try:
        conn = _get_db()
        now = datetime.now().isoformat()
        cursor = conn.execute(
            "INSERT INTO memory_space (content, created_at, updated_at, source) VALUES (?, ?, ?, ?)",
            (content, now, now, source),
        )
        conn.commit()
        item_id = cursor.lastrowid
        conn.close()
        logger.info(f"记忆空间新增: id={item_id}, content={content[:30]}...")
        return {"success": True, "id": item_id, "content": content}
    except Exception as e:
        return {"success": False, "error": str(e)}


def remove_memory(memory_id: int) -> dict:
    """删除记忆空间条目"""
    try:
        conn = _get_db()
        conn.execute("DELETE FROM memory_space WHERE id = ?", (memory_id,))
        conn.commit()
        affected = conn.total_changes
        conn.close()
        if affected > 0:
            logger.info(f"记忆空间删除: id={memory_id}")
            return {"success": True, "id": memory_id}
        return {"success": False, "error": "条目不存在"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_memory(memory_id: int, content: str) -> dict:
    """更新记忆空间条目"""
    try:
        conn = _get_db()
        now = datetime.now().isoformat()
        cursor = conn.execute(
            "UPDATE memory_space SET content = ?, updated_at = ? WHERE id = ?",
            (content, now, memory_id),
        )
        conn.commit()
        conn.close()
        if cursor.rowcount > 0:
            logger.info(f"记忆空间更新: id={memory_id}")
            return {"success": True, "id": memory_id, "content": content}
        return {"success": False, "error": "条目不存在"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_memories() -> dict:
    """列出所有记忆空间条目"""
    try:
        conn = _get_db()
        rows = conn.execute(
            "SELECT id, content, created_at, updated_at, source FROM memory_space ORDER BY id ASC"
        ).fetchall()
        conn.close()
        items = [dict(row) for row in rows]
        return {"success": True, "items": items, "count": len(items)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_memory_context_block() -> str:
    """获取记忆空间上下文文本（注入到对话上下文）"""
    result = list_memories()
    if not result.get("success") or not result.get("items"):
        return ""
    lines = []
    for item in result["items"]:
        lines.append(f"[{item['id']}] {item['content']}")
    return "\n".join(lines)

import os
import json
import sqlite3
from src.system.config import get_current_instance_config
from src.system.fingerprint import generate_fingerprint, get_utc_now
from src.tools.key_tools import get_current_keys_dir, BUILT_IN_KEYS


def get_db():
    instance = get_current_instance_config()
    db_path = instance["db_path"]
    if not os.path.isabs(db_path):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        db_path = os.path.join(base_dir, db_path)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _key_exists(key: str) -> bool:
    keys_dir = get_current_keys_dir()
    key_path = os.path.join(keys_dir, key)
    return os.path.isdir(key_path)


def _update_summary(key: str, summary_item: str, mode: str = "add") -> dict:
    try:
        keys_dir = get_current_keys_dir()
        summary_file = os.path.join(keys_dir, key, "summary.json")

        with open(summary_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if mode == "add":
            items = data.get("summary", "").split("\n") if data.get("summary") else []
            items.append(summary_item)
            data["summary"] = "\n".join([i for i in items if i])
        elif mode == "remove":
            items = data.get("summary", "").split("\n") if data.get("summary") else []
            items = [i for i in items if i != summary_item]
            data["summary"] = "\n".join([i for i in items if i])

        data["updated_at"] = get_utc_now()

        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def add_memory_to_key(
    key: str, memory: str, tag: str, summary_item: str, base_score: float = 0.5
) -> dict:
    try:
        if not memory:
            return {"success": False, "error": "EMPTY_MEMORY_ERROR"}

        if not _key_exists(key):
            return {"success": False, "error": "KEY_NOT_FOUND"}

        fingerprint = generate_fingerprint(memory)
        now = get_utc_now()

        conn = get_db()
        # 检查是否已存在相同fingerprint的记忆
        existing = conn.execute(
            "SELECT key FROM memory WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()

        if existing:
            existing_key = existing["key"]
            conn.close()
            if existing_key == key:
                # 相同key，记忆已存在，返回成功
                return {
                    "success": True,
                    "key": key,
                    "added": {
                        "fingerprint": fingerprint,
                        "memory": memory,
                        "tag": tag,
                        "summary_item": summary_item,
                    },
                    "already_exists": True,
                }
            else:
                # 不同key，返回错误
                return {"success": False, "error": "FP_EXISTS_IN_OTHER_KEY"}

        conn.execute(
            "INSERT INTO memory (fingerprint, key, memory, tag, summary_item, created_at, updated_at, base_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (fingerprint, key, memory, tag, summary_item, now, now, base_score),
        )
        conn.commit()
        conn.close()

        _update_summary(key, summary_item, mode="add")

        return {
            "success": True,
            "key": key,
            "added": {
                "fingerprint": fingerprint,
                "memory": memory,
                "tag": tag,
                "summary_item": summary_item,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def replace_memory_in_key(
    key: str, old_fingerprint: str, new_memory: str, new_tag: str, new_summary_item: str
) -> dict:
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM memory WHERE fingerprint = ? AND key = ?",
            (old_fingerprint, key),
        ).fetchone()

        if not row:
            conn.close()
            return {"success": False, "error": "FP_NOT_IN_KEY"}

        old_summary_item = (
            row["summary_item"] if row["summary_item"] is not None else ""
        ) or new_summary_item
        old_base_score = row["base_score"] if row["base_score"] is not None else 0.5
        old_recall_count = row["recall_count"] if row["recall_count"] is not None else 0
        old_semantic_status = (
            row["semantic_status"] if row["semantic_status"] is not None else "valid"
        )

        new_fingerprint = generate_fingerprint(new_memory)
        now = get_utc_now()

        # Insert new memory FIRST (safe: if this fails, old memory is untouched)
        conn.execute(
            "INSERT INTO memory (fingerprint, key, memory, tag, summary_item, created_at, updated_at, base_score, recall_count, semantic_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_fingerprint,
                key,
                new_memory,
                new_tag,
                new_summary_item,
                now,
                now,
                old_base_score,
                old_recall_count,
                old_semantic_status,
            ),
        )

        # Redirect edges from old to new fingerprint
        conn.execute(
            "UPDATE edges SET from_fingerprint = ? WHERE from_fingerprint = ?",
            (new_fingerprint, old_fingerprint),
        )
        conn.execute(
            "UPDATE edges SET to_fingerprint = ? WHERE to_fingerprint = ?",
            (new_fingerprint, old_fingerprint),
        )

        # Only AFTER insert succeeds, delete old memory
        conn.execute("DELETE FROM memory WHERE fingerprint = ?", (old_fingerprint,))

        conn.commit()
        conn.close()

        _update_summary(key, old_summary_item, mode="remove")
        _update_summary(key, new_summary_item, mode="add")

        return {
            "success": True,
            "key": key,
            "deleted_fingerprint": old_fingerprint,
            "added": {
                "fingerprint": new_fingerprint,
                "memory": new_memory,
                "tag": new_tag,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_memory_from_key(key: str, fingerprint: str) -> dict:
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM memory WHERE fingerprint = ? AND key = ?", (fingerprint, key)
        ).fetchone()

        if not row:
            conn.close()
            return {"success": False, "error": "FP_NOT_IN_KEY"}

        old_summary_item = row.get("summary_item")

        conn.execute("DELETE FROM memory WHERE fingerprint = ?", (fingerprint,))
        conn.execute(
            "DELETE FROM edges WHERE from_fingerprint = ? OR to_fingerprint = ?",
            (fingerprint, fingerprint),
        )
        conn.commit()
        conn.close()

        if old_summary_item:
            _update_summary(key, old_summary_item, mode="remove")

        return {"success": True, "key": key, "deleted_fingerprint": fingerprint}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_memory_by_key(key: str) -> dict:
    try:
        if not _key_exists(key):
            return {"success": False, "error": "KEY_NOT_FOUND"}

        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM memory WHERE key = ? ORDER BY created_at DESC", (key,)
        ).fetchall()
        conn.close()

        memories = [dict(row) for row in rows]
        return {"success": True, "key": key, "memories": memories}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_memories_by_key_sorted(key: str, limit: int = 50) -> dict:
    """按可见度和权重排序获取key下的记忆，限制数量"""
    try:
        if not _key_exists(key):
            return {"success": False, "error": "KEY_NOT_FOUND"}

        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM memory WHERE key = ? ORDER BY visibility DESC, weight DESC LIMIT ?",
            (key, limit),
        ).fetchall()
        conn.close()

        memories = [dict(row) for row in rows]
        return {"success": True, "key": key, "memories": memories}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_memory_by_fingerprint(fingerprint: str) -> dict:
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM memory WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        conn.close()

        if row:
            return {"success": True, "memory": dict(row)}
        return {"success": False, "error": "FP_NOT_FOUND"}
    except Exception as e:
        return {"success": False, "error": str(e)}

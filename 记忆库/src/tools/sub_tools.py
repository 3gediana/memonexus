import sqlite3
from src.system.config import get_current_instance_config
from src.system.fingerprint import get_utc_now


def get_sub_db():
    instance = get_current_instance_config()
    conn = sqlite3.connect(instance["sub_db_path"], timeout=10)
    conn.row_factory = sqlite3.Row
    conn.text_factory = str
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def insert_sub(raw_message: str, turn_index: int) -> dict:
    conn = None
    try:
        now = get_utc_now()
        conn = get_sub_db()
        cursor = conn.execute(
            "INSERT INTO sub (raw_message, created_at, turn_index) VALUES (?, ?, ?)",
            (raw_message, now, turn_index),
        )
        sub_id = cursor.lastrowid
        conn.commit()

        return {"success": True, "id": sub_id, "created_at": now}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        if conn:
            conn.close()


def query_sub_by_time(start: str, end: str) -> dict:
    try:
        if len(end) == 10:
            end = end + "T23:59:59"
        conn = get_sub_db()
        rows = conn.execute(
            "SELECT * FROM sub WHERE created_at BETWEEN ? AND ? ORDER BY created_at ASC",
            (start, end),
        ).fetchall()
        conn.close()

        items = [dict(row) for row in rows]
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_sub(limit: int = 50, offset: int = 0) -> dict:
    try:
        conn = get_sub_db()
        rows = conn.execute(
            "SELECT * FROM sub ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        conn.close()

        items = [dict(row) for row in rows]
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "error": str(e)}

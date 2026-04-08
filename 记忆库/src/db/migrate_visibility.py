"""
数据库迁移脚本：memory表新增 visibility 字段
"""

import sqlite3
from src.db.init import get_db, get_current_db_paths


def migrate_visibility() -> dict:
    try:
        paths = get_current_db_paths()
        db_path = paths["db_path"]

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(memory)")
        columns = [col[1] for col in cursor.fetchall()]

        if "visibility" not in columns:
            cursor.execute("ALTER TABLE memory ADD COLUMN visibility REAL DEFAULT 1.0")
            print("Added column: visibility")

        conn.commit()
        conn.close()

        return {"success": True, "message": "Visibility migration completed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    result = migrate_visibility()
    print(result)

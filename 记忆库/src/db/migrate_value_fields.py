"""
数据库迁移脚本：memory表添加价值评估相关字段
"""

import sqlite3
from src.db.init import get_current_db_paths


def migrate_value_fields() -> dict:
    try:
        paths = get_current_db_paths()
        db_path = paths["db_path"]

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(memory)")
        memory_columns = [col[1] for col in cursor.fetchall()]

        if "recall_count" not in memory_columns:
            cursor.execute(
                "ALTER TABLE memory ADD COLUMN recall_count INTEGER DEFAULT 0"
            )
            print("Added column: memory.recall_count")

        if "hit_count" not in memory_columns:
            cursor.execute("ALTER TABLE memory ADD COLUMN hit_count INTEGER DEFAULT 0")
            print("Added column: memory.hit_count")

        if "direct_recall_count" not in memory_columns:
            cursor.execute(
                "ALTER TABLE memory ADD COLUMN direct_recall_count INTEGER DEFAULT 0"
            )
            print("Added column: memory.direct_recall_count")

        if "total_recall_count" not in memory_columns:
            cursor.execute(
                "ALTER TABLE memory ADD COLUMN total_recall_count INTEGER DEFAULT 0"
            )
            print("Added column: memory.total_recall_count")

        conn.commit()
        conn.close()

        return {"success": True, "message": "Value fields migration completed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    result = migrate_value_fields()
    print(result)

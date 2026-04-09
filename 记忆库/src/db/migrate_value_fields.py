"""
数据库迁移脚本：memory表添加价值评估相关字段
"""

import sqlite3
from src.db.init import get_current_db_paths
from src.db.schema import MEMORY_COLUMNS_MIGRATION


def migrate_value_fields() -> dict:
    try:
        paths = get_current_db_paths()
        db_path = paths["db_path"]

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(memory)")
        memory_columns = [col[1] for col in cursor.fetchall()]

        # 定义需要添加的列
        value_columns = [
            "recall_count",
            "hit_count",
            "direct_recall_count",
            "total_recall_count",
        ]

        for col_name, col_def in MEMORY_COLUMNS_MIGRATION:
            if col_name in value_columns and col_name not in memory_columns:
                cursor.execute(f"ALTER TABLE memory ADD COLUMN {col_name} {col_def}")
                print(f"Added column: memory.{col_name}")

        conn.commit()
        conn.close()

        return {"success": True, "message": "Value fields migration completed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    result = migrate_value_fields()
    print(result)

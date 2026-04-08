"""
数据库迁移脚本：edges表新增 recall_count、hit_count、effective_strength 字段
"""

import sqlite3
from src.db.init import get_db, get_current_db_paths


def migrate_edge_strength() -> dict:
    try:
        paths = get_current_db_paths()
        db_path = paths["db_path"]

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查当前edges表列
        cursor.execute("PRAGMA table_info(edges)")
        columns = [col[1] for col in cursor.fetchall()]

        if "recall_count" not in columns:
            cursor.execute(
                "ALTER TABLE edges ADD COLUMN recall_count INTEGER DEFAULT 0"
            )
            print("Added column: recall_count")

        if "hit_count" not in columns:
            cursor.execute("ALTER TABLE edges ADD COLUMN hit_count INTEGER DEFAULT 0")
            print("Added column: hit_count")

        if "effective_strength" not in columns:
            # 默认0.5，实际使用时calibrator会根据strength初始化
            cursor.execute(
                "ALTER TABLE edges ADD COLUMN effective_strength REAL DEFAULT 0.5"
            )
            print("Added column: effective_strength")

        # 用当前strength值填充effective_strength（已有边的初始化）
        cursor.execute(
            "UPDATE edges SET effective_strength = strength WHERE recall_count = 0"
        )
        print(f"Initialized effective_strength for {cursor.rowcount} edges")

        conn.commit()
        conn.close()

        return {"success": True, "message": "Edge strength migration completed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    result = migrate_edge_strength()
    print(result)

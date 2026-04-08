"""
数据库迁移脚本：memory表新增 summary_item 字段
summary_item 用于在 replace 操作时正确移除旧的 summary 条目
"""

import sqlite3
from src.db.init import get_current_db_paths


def migrate_summary_item() -> dict:
    try:
        paths = get_current_db_paths()
        db_path = paths["db_path"]

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        columns = [
            row[1] for row in cursor.execute("PRAGMA table_info(memory)").fetchall()
        ]

        if "summary_item" not in columns:
            cursor.execute("ALTER TABLE memory ADD COLUMN summary_item TEXT DEFAULT ''")
            print("Added column: summary_item")

            # 为已有记忆填充 summary_item（默认使用 memory 前50字符）
            cursor.execute(
                "UPDATE memory SET summary_item = substr(memory, 1, 50) WHERE summary_item = '' OR summary_item IS NULL"
            )
            updated = cursor.rowcount
            print(f"Backfilled summary_item for {updated} existing memories")

        conn.commit()
        conn.close()
        return {
            "success": True,
            "message": "summary_item column added/backfilled successfully",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    result = migrate_summary_item()
    print(result)

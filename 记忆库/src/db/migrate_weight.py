"""
数据库迁移脚本：增加 weight 和 last_recall_at 字段
"""
import sqlite3
from src.db.init import get_db, get_current_db_paths


def migrate_weight() -> dict:
    """
    执行迁移：
    ALTER TABLE memory ADD COLUMN weight REAL DEFAULT 0.5;
    ALTER TABLE memory ADD COLUMN last_recall_at TEXT;
    CREATE INDEX idx_memory_weight ON memory(weight);
    CREATE INDEX idx_memory_last_recall ON memory(last_recall_at);
    """
    try:
        paths = get_current_db_paths()
        db_path = paths["db_path"]

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 检查 weight 列是否存在
        cursor.execute("PRAGMA table_info(memory)")
        columns = [col[1] for col in cursor.fetchall()]

        if "weight" not in columns:
            cursor.execute("ALTER TABLE memory ADD COLUMN weight REAL DEFAULT 0.5")
            print("Added column: weight")

        if "last_recall_at" not in columns:
            cursor.execute("ALTER TABLE memory ADD COLUMN last_recall_at TEXT")
            print("Added column: last_recall_at")

        # 创建索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_weight ON memory(weight)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_last_recall ON memory(last_recall_at)")
        print("Created indexes: idx_memory_weight, idx_memory_last_recall")

        conn.commit()
        conn.close()

        return {"success": True, "message": "Migration completed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def rollback_weight() -> dict:
    """
    回滚迁移（仅用于测试）
    """
    try:
        paths = get_current_db_paths()
        db_path = paths["db_path"]

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("DROP INDEX IF EXISTS idx_memory_weight")
        cursor.execute("DROP INDEX IF EXISTS idx_memory_last_recall")
        # SQLite 不支持 DROP COLUMN，需要重建表
        # 此处仅作标记，实际生产不应删除列

        conn.commit()
        conn.close()

        return {"success": True, "message": "Rollback completed (indexes dropped)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        result = rollback_weight()
    else:
        result = migrate_weight()
    print(result)
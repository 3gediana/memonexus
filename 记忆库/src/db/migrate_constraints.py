"""
数据库迁移脚本：为现有数据库添加 CHECK 约束和 ON DELETE CASCADE 外键
SQLite 不支持直接 ALTER TABLE 添加约束，需要重建表
"""

import sqlite3
import os
from src.db.init import get_current_db_paths


def migrate_constraints() -> dict:
    try:
        paths = get_current_db_paths()
        db_path = paths["db_path"]

        # 备份原数据库
        backup_path = db_path + ".backup"
        if os.path.exists(db_path):
            import shutil
            shutil.copy2(db_path, backup_path)
            print(f"Backed up database to: {backup_path}")

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 1. 为 memory 表添加 semantic_status 的 CHECK 约束
        # SQLite 不支持 ALTER TABLE ADD CONSTRAINT，需要重建表
        _add_semantic_status_check(cursor)

        # 2. 为 edges 表添加 strength 的 CHECK 约束和 ON DELETE CASCADE
        _add_edges_constraints(cursor)

        # 3. 为 memory_cluster_members 表添加 ON DELETE CASCADE
        _add_cluster_members_constraints(cursor)

        conn.commit()
        conn.close()

        return {"success": True, "message": "Constraints migration completed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _add_semantic_status_check(cursor):
    """为 memory 表的 semantic_status 添加 CHECK 约束"""
    # 检查当前是否有不合法的值
    cursor.execute(
        "SELECT COUNT(*) FROM memory WHERE semantic_status NOT IN ('valid', 'completed', 'expired')"
    )
    invalid_count = cursor.fetchone()[0]
    if invalid_count > 0:
        print(f"Warning: Found {invalid_count} rows with invalid semantic_status, will be set to 'valid'")
        cursor.execute(
            "UPDATE memory SET semantic_status = 'valid' WHERE semantic_status NOT IN ('valid', 'completed', 'expired')"
        )

    # 重建表添加 CHECK 约束
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_new (
            fingerprint TEXT PRIMARY KEY,
            key TEXT NOT NULL,
            memory TEXT NOT NULL,
            tag TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            summary_item TEXT DEFAULT '',
            visibility REAL DEFAULT 1.0,
            base_score REAL DEFAULT 0.5,
            recall_count INTEGER DEFAULT 0,
            value_score REAL DEFAULT 0.5,
            semantic_status TEXT DEFAULT 'valid' CHECK (semantic_status IN ('valid', 'completed', 'expired')),
            weight REAL DEFAULT 0.5,
            last_recall_at INTEGER,
            hit_count INTEGER DEFAULT 0,
            direct_recall_count INTEGER DEFAULT 0,
            total_recall_count INTEGER DEFAULT 0
        )
    """)
    cursor.execute("INSERT INTO memory_new SELECT * FROM memory")
    cursor.execute("DROP TABLE memory")
    cursor.execute("ALTER TABLE memory_new RENAME TO memory")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_key ON memory(key)")
    print("Added CHECK constraint for memory.semantic_status")


def _add_edges_constraints(cursor):
    """为 edges 表添加 strength CHECK 约束和 ON DELETE CASCADE"""
    # 检查当前是否有不合法的 strength 值
    cursor.execute(
        "SELECT COUNT(*) FROM edges WHERE strength NOT IN (0.9, 0.6, 0.3)"
    )
    invalid_count = cursor.fetchone()[0]
    if invalid_count > 0:
        print(f"Warning: Found {invalid_count} edges with invalid strength, will be clamped to nearest valid value")
        # 将不合法的值映射到最接近的有效值
        cursor.execute("""
            UPDATE edges SET strength = (
                CASE
                    WHEN strength >= 0.75 THEN 0.9
                    WHEN strength >= 0.45 THEN 0.6
                    ELSE 0.3
                END
            )
            WHERE strength NOT IN (0.9, 0.6, 0.3)
        """)

    # 重建表添加 CHECK 和 ON DELETE CASCADE
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS edges_new (
            from_fingerprint TEXT NOT NULL,
            to_fingerprint TEXT NOT NULL,
            strength REAL NOT NULL CHECK (strength IN (0.9, 0.6, 0.3)),
            reason TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            recall_count INTEGER DEFAULT 0,
            hit_count INTEGER DEFAULT 0,
            effective_strength REAL DEFAULT 0.5,
            PRIMARY KEY (from_fingerprint, to_fingerprint),
            FOREIGN KEY (from_fingerprint) REFERENCES memory(fingerprint) ON DELETE CASCADE,
            FOREIGN KEY (to_fingerprint) REFERENCES memory(fingerprint) ON DELETE CASCADE
        )
    """)
    cursor.execute("INSERT INTO edges_new SELECT * FROM edges")
    cursor.execute("DROP TABLE edges")
    cursor.execute("ALTER TABLE edges_new RENAME TO edges")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_edge_from ON edges(from_fingerprint)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_edge_to ON edges(to_fingerprint)")
    print("Added CHECK constraint and ON DELETE CASCADE for edges")


def _add_cluster_members_constraints(cursor):
    """为 memory_cluster_members 表添加 ON DELETE CASCADE"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_cluster_members_new (
            cluster_id TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            added_at TEXT NOT NULL,
            PRIMARY KEY (cluster_id, fingerprint),
            FOREIGN KEY (cluster_id) REFERENCES memory_clusters(cluster_id) ON DELETE CASCADE,
            FOREIGN KEY (fingerprint) REFERENCES memory(fingerprint) ON DELETE CASCADE
        )
    """)
    cursor.execute("INSERT INTO memory_cluster_members_new SELECT * FROM memory_cluster_members")
    cursor.execute("DROP TABLE memory_cluster_members")
    cursor.execute("ALTER TABLE memory_cluster_members_new RENAME TO memory_cluster_members")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_cluster_member_fp ON memory_cluster_members(fingerprint)")
    print("Added ON DELETE CASCADE for memory_cluster_members")


if __name__ == "__main__":
    result = migrate_constraints()
    print(result)

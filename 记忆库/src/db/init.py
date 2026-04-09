import sqlite3
import os
from src.system.config import load_config, get_current_instance_config


def get_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_current_db_paths() -> dict:
    instance = get_current_instance_config()
    return {"db_path": instance["db_path"], "sub_db_path": instance["sub_db_path"]}


def init_database(db_path: str = None) -> dict:
    try:
        if db_path is None:
            paths = get_current_db_paths()
            db_path = paths["db_path"]

        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory (
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
                semantic_status TEXT DEFAULT 'valid',
                weight REAL DEFAULT 0.5,
                last_recall_at INTEGER
            )
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_key ON memory(key)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                from_fingerprint TEXT NOT NULL,
                to_fingerprint TEXT NOT NULL,
                strength REAL NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                recall_count INTEGER DEFAULT 0,
                hit_count INTEGER DEFAULT 0,
                effective_strength REAL DEFAULT 0.5,
                PRIMARY KEY (from_fingerprint, to_fingerprint),
                FOREIGN KEY (from_fingerprint) REFERENCES memory(fingerprint),
                FOREIGN KEY (to_fingerprint) REFERENCES memory(fingerprint)
            )
        """)

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_edge_from ON edges(from_fingerprint)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_edge_to ON edges(to_fingerprint)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_clusters (
                cluster_id TEXT PRIMARY KEY,
                key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                merged_at TEXT,
                status TEXT DEFAULT 'active'
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_cluster_members (
                cluster_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                added_at TEXT NOT NULL,
                PRIMARY KEY (cluster_id, fingerprint),
                FOREIGN KEY (cluster_id) REFERENCES memory_clusters(cluster_id),
                FOREIGN KEY (fingerprint) REFERENCES memory(fingerprint)
            )
        """)

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cluster_member_fp ON memory_cluster_members(fingerprint)"
        )

        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_space (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT DEFAULT 'user'
            )
        """)

        # 向后兼容：为已有表添加缺失列
        _migrate_memory_columns(conn)

        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _migrate_memory_columns(conn):
    """为已有 memory 表添加新列（如果不存在）"""
    cursor = conn.execute("PRAGMA table_info(memory)")
    existing = {row["name"] for row in cursor.fetchall()}

    migrations = [
        ("visibility", "REAL DEFAULT 1.0"),
        ("base_score", "REAL DEFAULT 0.5"),
        ("recall_count", "INTEGER DEFAULT 0"),
        ("value_score", "REAL DEFAULT 0.5"),
        ("semantic_status", "TEXT DEFAULT 'valid'"),
        ("weight", "REAL DEFAULT 0.5"),
        ("last_recall_at", "INTEGER"),
    ]

    for col_name, col_def in migrations:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE memory ADD COLUMN {col_name} {col_def}")


def init_sub_database(sub_db_path: str = None) -> dict:
    try:
        if sub_db_path is None:
            paths = get_current_db_paths()
            sub_db_path = paths["sub_db_path"]

        os.makedirs(os.path.dirname(sub_db_path), exist_ok=True)
        conn = sqlite3.connect(sub_db_path)
        conn.execute("PRAGMA foreign_keys = ON")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS sub (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_message TEXT NOT NULL,
                created_at TEXT NOT NULL,
                turn_index INTEGER NOT NULL
            )
        """)

        conn.commit()
        conn.close()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_table_schema(db_path: str, table_name: str) -> dict:
    try:
        conn = get_db(db_path)
        cursor = conn.execute(f"PRAGMA table_info({table_name})")
        columns = []
        for row in cursor.fetchall():
            col = {
                "name": row["name"],
                "type": row["type"],
                "notnull": bool(row["notnull"]),
                "pk": bool(row["pk"]),
            }
            columns.append(col)

        indexes = []
        cursor = conn.execute(f"PRAGMA index_list({table_name})")
        for row in cursor.fetchall():
            idx_name = row["name"]
            idx_cursor = conn.execute(f"PRAGMA index_info({idx_name})")
            idx_cols = [r["name"] for r in idx_cursor.fetchall()]
            indexes.append({"name": idx_name, "columns": idx_cols})

        conn.close()
        return {
            "success": True,
            "table": table_name,
            "columns": columns,
            "indexes": indexes,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

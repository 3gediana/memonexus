"""
数据库共享常量定义
"""

MEMORY_COLUMNS_MIGRATION = [
    ("visibility", "REAL DEFAULT 1.0"),
    ("base_score", "REAL DEFAULT 0.5"),
    ("recall_count", "INTEGER DEFAULT 0"),
    ("value_score", "REAL DEFAULT 0.5"),
    ("semantic_status", "TEXT DEFAULT 'valid'"),
    ("weight", "REAL DEFAULT 0.5"),
    ("last_recall_at", "INTEGER"),
    ("hit_count", "INTEGER DEFAULT 0"),
    ("direct_recall_count", "INTEGER DEFAULT 0"),
    ("total_recall_count", "INTEGER DEFAULT 0"),
]

VALID_SEMANTIC_STATUSES = {"valid", "completed", "expired"}
VALID_EDGE_STRENGTHS = {0.9, 0.6, 0.3}

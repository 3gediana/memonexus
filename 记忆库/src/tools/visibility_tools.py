"""
可见度工具 - 记忆可见度管理
"""

import math
from src.tools.memory_tools import get_db
from src.system.logger import get_module_logger

logger = get_module_logger("visibility")

EVENT_SCORES = {
    "associated_recall": 0.6,
    "direct_hit": 1.0,
    "direct_miss": 0.2,
}

ALPHA = 0.2
K_CONN = 0.05
HIDDEN_THRESHOLD = 0.3


def get_connectivity_factor(fingerprint: str) -> float:
    try:
        conn = get_db()
    except Exception:
        return 1.0
    try:
        row = conn.execute(
            """SELECT COUNT(*) as edge_count, AVG(e.effective_strength) as avg_effective
               FROM edges e
               WHERE e.from_fingerprint = ? OR e.to_fingerprint = ?""",
            (fingerprint, fingerprint),
        ).fetchone()

        if not row or row["edge_count"] == 0:
            return 1.0

        edge_count = row["edge_count"]
        avg_effective = (
            row["avg_effective"] if row["avg_effective"] is not None else 0.5
        )

        c_conn = 1.0 + K_CONN * math.log(1.0 + edge_count * avg_effective)
        return c_conn
    except Exception:
        return 1.0
    finally:
        conn.close()


def update_visibility(fingerprint: str, event_type: str) -> dict:
    logger.debug(f"更新可见度: {fingerprint[:8]}... event={event_type}")
    try:
        conn = get_db()
    except Exception as e:
        return {"success": False, "error": str(e)}
    try:
        row = conn.execute(
            "SELECT visibility FROM memory WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()

        if not row:
            return {"success": False, "error": "FP_NOT_FOUND"}

        old_visibility = row["visibility"] if row["visibility"] is not None else 1.0
        event_score = EVENT_SCORES.get(event_type, 0.5)
        c_conn = get_connectivity_factor(fingerprint)

        new_visibility = ALPHA * event_score * c_conn + (1 - ALPHA) * old_visibility
        new_visibility = max(0.0, min(1.0, new_visibility))

        conn.execute(
            "UPDATE memory SET visibility = ? WHERE fingerprint = ?",
            (new_visibility, fingerprint),
        )
        conn.commit()

        return {
            "success": True,
            "fingerprint": fingerprint,
            "old_visibility": old_visibility,
            "new_visibility": new_visibility,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def is_visible(fingerprint: str) -> bool:
    try:
        conn = get_db()
    except Exception:
        return True
    try:
        row = conn.execute(
            "SELECT visibility FROM memory WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()

        if not row:
            return False

        visibility = row["visibility"] if row["visibility"] is not None else 1.0
        return visibility >= HIDDEN_THRESHOLD
    except Exception:
        return True
    finally:
        conn.close()


def get_visible_memories(key: str) -> list:
    try:
        conn = get_db()
    except Exception:
        return []
    try:
        rows = conn.execute(
            "SELECT fingerprint, tag FROM memory WHERE key = ? AND (visibility IS NULL OR visibility >= ?)",
            (key, HIDDEN_THRESHOLD),
        ).fetchall()

        return [{"fingerprint": row["fingerprint"], "tag": row["tag"]} for row in rows]
    except Exception:
        return []
    finally:
        conn.close()


def calculate_visibility_with_value(fingerprint: str) -> float:
    """计算考虑记忆价值的可见度"""
    from src.tools.value_assessor import get_value_assessor

    assessor = get_value_assessor()
    value_result = assessor.calculate_value(fingerprint)

    if not value_result["success"]:
        return 1.0

    memory_value = value_result["value"]

    try:
        conn = get_db()
    except Exception:
        return 1.0
    try:
        row = conn.execute(
            "SELECT visibility FROM memory WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()

        base_visibility = (
            row["visibility"] if row and row["visibility"] is not None else 1.0
        )

        adjusted_visibility = base_visibility * (0.5 + 0.5 * memory_value)

        return adjusted_visibility
    except Exception:
        return 1.0
    finally:
        conn.close()

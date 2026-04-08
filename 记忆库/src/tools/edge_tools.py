import sqlite3
from src.system.config import get_current_instance_config
from src.system.fingerprint import get_utc_now
from src.tools.memory_tools import get_db


VALID_STRENGTHS = {0.9, 0.6, 0.3}


def _fp_exists(fingerprint: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM memory WHERE fingerprint = ?", (fingerprint,)
    ).fetchone()
    conn.close()
    return row is not None


def create_edges(edges: list[dict]) -> dict:
    try:
        conn = get_db()
        now = get_utc_now()
        created_edges = []

        for edge in edges:
            from_fp = edge["from_fingerprint"]
            to_fp = edge["to_fingerprint"]
            strength = edge["strength"]
            reason = edge["reason"]

            if from_fp == to_fp:
                conn.close()
                return {"success": False, "error": "SELF_LOOP_ERROR"}

            if strength not in VALID_STRENGTHS:
                conn.close()
                return {"success": False, "error": "INVALID_STRENGTH"}

            if not _fp_exists(from_fp) or not _fp_exists(to_fp):
                conn.close()
                return {"success": False, "error": "FP_NOT_FOUND"}

            existing = conn.execute(
                "SELECT recall_count, hit_count, effective_strength FROM edges WHERE from_fingerprint = ? AND to_fingerprint = ?",
                (from_fp, to_fp),
            ).fetchone()

            if existing is None:
                conn.execute(
                    "INSERT INTO edges (from_fingerprint, to_fingerprint, strength, effective_strength, reason, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (from_fp, to_fp, strength, strength, reason, now, now),
                )
            else:
                recall_count = existing["recall_count"]
                hit_count = existing["hit_count"]
                effective_strength = existing["effective_strength"]
                conn.execute(
                    "UPDATE edges SET strength = ?, effective_strength = ?, reason = ?, updated_at = ? WHERE from_fingerprint = ? AND to_fingerprint = ?",
                    (strength, effective_strength, reason, now, from_fp, to_fp),
                )
            created_edges.append({"from": from_fp, "to": to_fp})

        conn.commit()
        conn.close()

        # Invalidate PageRank cache and mark clusters as changed
        try:
            from src.tools.value_assessor import _assessor_instance

            if _assessor_instance:
                _assessor_instance._pagerank_cache.clear()
        except Exception:
            pass

        try:
            from src.tools.cluster_engine import get_cluster_engine

            get_cluster_engine().mark_changed()
        except Exception:
            pass

        return {
            "success": True,
            "created_count": len(created_edges),
            "created_edges": created_edges,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_edges(edges: list[dict]) -> dict:
    try:
        conn = get_db()
        deleted_edges = []

        for edge in edges:
            from_fp = edge["from_fingerprint"]
            to_fp = edge["to_fingerprint"]

            cursor = conn.execute(
                "DELETE FROM edges WHERE from_fingerprint = ? AND to_fingerprint = ?",
                (from_fp, to_fp),
            )
            if cursor.rowcount > 0:
                deleted_edges.append({"from": from_fp, "to": to_fp})

        conn.commit()
        conn.close()

        return {
            "success": True,
            "deleted_count": len(deleted_edges),
            "deleted_edges": deleted_edges,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_edges_by_fingerprint(fingerprint: str) -> dict:
    try:
        conn = get_db()
        rows = conn.execute(
            "SELECT * FROM edges WHERE from_fingerprint = ? OR to_fingerprint = ?",
            (fingerprint, fingerprint),
        ).fetchall()
        conn.close()

        edges = [dict(row) for row in rows]
        return {"success": True, "fingerprint": fingerprint, "edges": edges}
    except Exception as e:
        return {"success": False, "error": str(e)}

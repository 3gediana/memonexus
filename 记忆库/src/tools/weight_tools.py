"""
权重管理工具 - 连通性和动态k计算
"""

import math
from dataclasses import dataclass
from src.tools.memory_tools import get_db

DEFAULT_K_CONN = 0.05


def get_connectivity_factor(fingerprint: str, k_conn: float = None) -> float:
    """
    计算某条记忆的关联因子 C_conn

    C_conn = 1 + k_conn × log(1 + edge_count × avg_effective_strength)

    Args:
        fingerprint: 记忆指纹
        k_conn: 关联性系数，若为None则使用默认值

    Returns:
        关联因子 C_conn（无关联时为1.0）
    """
    if k_conn is None:
        k_conn = DEFAULT_K_CONN

    try:
        conn = get_db()
    except Exception:
        return 1.0
    try:
        row = conn.execute(
            """
            SELECT
                COUNT(*) as edge_count,
                AVG(effective_strength) as avg_strength
            FROM edges
            WHERE from_fingerprint = ? OR to_fingerprint = ?
            """,
            (fingerprint, fingerprint),
        ).fetchone()

        if not row or row["edge_count"] == 0:
            return 1.0

        edge_count = row["edge_count"]
        avg_strength = row["avg_strength"] if row["avg_strength"] is not None else 0.0

        c_conn = 1.0 + k_conn * math.log(1.0 + edge_count * avg_strength)

        return c_conn
    except Exception:
        return 1.0
    finally:
        conn.close()


def calculate_dynamic_k(
    memory_weight: float,
    edge_strength: float,
    c_conn: float,
    min_k: int = 1,
    max_k: int = 5,
    base_topk: int = 2,
) -> int:
    """
    根据记忆权重和关联强度计算动态关联数

    score = memory_weight × edge_strength × C_conn
    dynamic_k = clamp(min_k + (max_k - min_k) × sigmoid(score / base_topk), min_k, max_k)

    Args:
        memory_weight: 记忆权重 (0.0-1.0)
        edge_strength: 边的关联强度 (0.0-1.0)
        c_conn: 关联因子 C_conn
        min_k: 最小关联数
        max_k: 最大关联数
        base_topk: 基准topk用于归一化

    Returns:
        动态计算的关联数量
    """
    score = memory_weight * edge_strength * c_conn
    sigmoid_score = 1 / (1 + math.exp(-score / base_topk))
    dynamic_k = min_k + (max_k - min_k) * sigmoid_score
    return max(min_k, min(max_k, round(dynamic_k)))


def get_memory_weight_info(fingerprint: str) -> dict:
    """
    获取记忆的权重信息

    Returns:
        weight, last_recall_at
    """
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT weight, last_recall_at FROM memory WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        conn.close()

        if not row:
            return {"success": False, "error": "FP_NOT_FOUND"}

        weight = row["weight"] if row["weight"] is not None else 0.5
        last_recall_at = row["last_recall_at"]

        return {
            "success": True,
            "fingerprint": fingerprint,
            "weight": weight,
            "last_recall_at": last_recall_at,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

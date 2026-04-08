"""
记忆簇管理服务
- 新记忆落位后，计算与已有簇的语义相似度
- 匹配到簇 → 加入该簇
- 无匹配 → 创建新簇
- 簇内记忆达到阈值 → 触发合并
"""

import json
import uuid
from datetime import datetime
from src.tools.association_scorer import get_scorer
from src.tools.memory_tools import get_db
from src.system.fingerprint import get_utc_now
from src.system.config import load_config


def _get_similarity_threshold() -> float:
    """获取相似度阈值（可配置，默认0.85）"""
    config = load_config()
    return config.get("cluster_similarity_threshold", 0.85)


def _get_merge_trigger_count() -> int:
    """触发合并的簇内记忆数量阈值（可配置，默认5）"""
    config = load_config()
    return config.get("cluster_merge_trigger_count", 5)


def assign_memory_to_cluster(
    fingerprint: str, key: str, memory_text: str, tag: str
) -> dict:
    """
    新记忆落位后，分配到合适的簇

    流程：
    1. 获取该 key 下所有活跃簇的代表记忆
    2. 计算新记忆与各簇的语义相似度
    3. 如果相似度 > 阈值 → 加入该簇
    4. 无匹配 → 创建新簇
    5. 检查簇是否达到合并阈值

    返回：
    - cluster_id: 分配的簇ID
    - merged: 是否触发了合并
    - merged_memories: 合并后的记忆（如果触发了合并）
    """
    threshold = _get_similarity_threshold()
    merge_trigger = _get_merge_trigger_count()

    conn = get_db()
    try:
        # 获取该 key 下所有活跃簇
        clusters = conn.execute(
            """
            SELECT c.cluster_id, m.fingerprint, m.memory, m.tag
            FROM memory_clusters c
            JOIN memory_cluster_members mcm ON c.cluster_id = mcm.cluster_id
            JOIN memory m ON mcm.fingerprint = m.fingerprint
            WHERE c.key = ? AND c.status = 'active'
            ORDER BY c.created_at DESC
            """,
            (key,),
        ).fetchall()

        # 按簇分组
        cluster_map = {}
        for row in clusters:
            cid = row["cluster_id"]
            if cid not in cluster_map:
                cluster_map[cid] = {
                    "cluster_id": cid,
                    "members": [],
                    "representative": None,
                }
            cluster_map[cid]["members"].append(
                {
                    "fingerprint": row["fingerprint"],
                    "memory": row["memory"],
                    "tag": row["tag"],
                }
            )
            # 用最新记忆作为代表（覆盖更新）
            cluster_map[cid]["representative"] = row["memory"]

        # 计算与新记忆的相似度
        scorer = get_scorer()
        best_cluster = None
        best_score = 0.0

        for cid, cluster in cluster_map.items():
            rep = cluster["representative"]
            if rep and scorer._model.is_available():
                score = scorer.compute_semantic_similarity(memory_text, rep)
                if score > best_score:
                    best_score = score
                    best_cluster = cid

        # 分配簇
        if best_cluster and best_score >= threshold:
            cluster_id = best_cluster
            # 加入簇
            conn.execute(
                "INSERT OR IGNORE INTO memory_cluster_members (cluster_id, fingerprint, added_at) VALUES (?, ?, ?)",
                (cluster_id, fingerprint, get_utc_now()),
            )
        else:
            # 创建新簇
            cluster_id = f"cluster_{uuid.uuid4().hex[:12]}"
            conn.execute(
                "INSERT INTO memory_clusters (cluster_id, key, created_at, status) VALUES (?, ?, ?, 'active')",
                (cluster_id, key, get_utc_now()),
            )
            conn.execute(
                "INSERT INTO memory_cluster_members (cluster_id, fingerprint, added_at) VALUES (?, ?, ?)",
                (cluster_id, fingerprint, get_utc_now()),
            )

        conn.commit()

        # 检查是否达到合并阈值
        member_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM memory_cluster_members WHERE cluster_id = ?",
            (cluster_id,),
        ).fetchone()["cnt"]

        merged = False
        merged_memories = []

        if member_count >= merge_trigger:
            # 触发合并
            merged_memories = conn.execute(
                """
                SELECT m.fingerprint, m.memory, m.tag, m.created_at
                FROM memory_cluster_members mcm
                JOIN memory m ON mcm.fingerprint = m.fingerprint
                WHERE mcm.cluster_id = ?
                ORDER BY m.created_at ASC
                """,
                (cluster_id,),
            ).fetchall()

            merged_memories = [dict(row) for row in merged_memories]
            merged = True

        return {
            "success": True,
            "cluster_id": cluster_id,
            "similarity_score": best_score,
            "member_count": member_count,
            "merged": merged,
            "merged_memories": merged_memories,
        }

    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def complete_cluster_merge(
    cluster_id: str, merged_fingerprint: str, merged_memory: str, merged_tag: str
) -> dict:
    """
    完成簇合并

    流程：
    1. 获取原簇成员的所有边
    2. 删除原簇内所有记忆（级联删除边）
    3. 插入合并后的新记忆
    4. 重定向边到新指纹（去重，取最大strength）
    5. 标记簇为已合并
    """
    conn = get_db()
    try:
        # 获取原簇成员
        members = conn.execute(
            "SELECT fingerprint FROM memory_cluster_members WHERE cluster_id = ?",
            (cluster_id,),
        ).fetchall()
        old_fps = [row["fingerprint"] for row in members]

        if not old_fps:
            return {"success": False, "error": "No members in cluster"}

        # 获取 key
        key = conn.execute(
            "SELECT key FROM memory_clusters WHERE cluster_id = ?",
            (cluster_id,),
        ).fetchone()["key"]

        # 先删除簇成员引用（解除外键约束）
        conn.execute(
            "DELETE FROM memory_cluster_members WHERE cluster_id = ?", (cluster_id,)
        )

        # 获取旧记忆的所有边（重定向用）
        placeholders = ",".join(["?"] * len(old_fps))
        outgoing_edges = conn.execute(
            f"""
            SELECT to_fingerprint, strength, reason, recall_count, hit_count, effective_strength
            FROM edges WHERE from_fingerprint IN ({placeholders})
            """,
            old_fps,
        ).fetchall()

        incoming_edges = conn.execute(
            f"""
            SELECT from_fingerprint, strength, reason, recall_count, hit_count, effective_strength
            FROM edges WHERE to_fingerprint IN ({placeholders})
            """,
            old_fps,
        ).fetchall()

        # 删除原记忆（级联删除边）
        for fp in old_fps:
            conn.execute("DELETE FROM memory WHERE fingerprint = ?", (fp,))

        # 插入合并后的记忆
        conn.execute(
            "INSERT INTO memory (fingerprint, key, memory, tag, created_at, updated_at, summary_item, visibility) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                merged_fingerprint,
                key,
                merged_memory,
                merged_tag,
                get_utc_now(),
                get_utc_now(),
                merged_memory[:50],
                1.0,
            ),
        )

        # 重定向出边（去重，取最大 strength）
        edge_map_out = {}
        for edge in outgoing_edges:
            to_fp = edge["to_fingerprint"]
            if (
                to_fp not in edge_map_out
                or edge["strength"] > edge_map_out[to_fp]["strength"]
            ):
                edge_map_out[to_fp] = edge

        for to_fp, edge in edge_map_out.items():
            conn.execute(
                "INSERT OR IGNORE INTO edges (from_fingerprint, to_fingerprint, strength, reason, recall_count, hit_count, effective_strength, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    merged_fingerprint,
                    to_fp,
                    edge["strength"],
                    edge["reason"],
                    edge["recall_count"],
                    edge["hit_count"],
                    edge["effective_strength"],
                    get_utc_now(),
                    get_utc_now(),
                ),
            )

        # 重定向入边（去重，取最大 strength）
        edge_map_in = {}
        for edge in incoming_edges:
            from_fp = edge["from_fingerprint"]
            if (
                from_fp not in edge_map_in
                or edge["strength"] > edge_map_in[from_fp]["strength"]
            ):
                edge_map_in[from_fp] = edge

        for from_fp, edge in edge_map_in.items():
            conn.execute(
                "INSERT OR IGNORE INTO edges (from_fingerprint, to_fingerprint, strength, reason, recall_count, hit_count, effective_strength, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    from_fp,
                    merged_fingerprint,
                    edge["strength"],
                    edge["reason"],
                    edge["recall_count"],
                    edge["hit_count"],
                    edge["effective_strength"],
                    get_utc_now(),
                    get_utc_now(),
                ),
            )

        # 更新簇状态
        conn.execute(
            "UPDATE memory_clusters SET status = 'merged', merged_at = ? WHERE cluster_id = ?",
            (get_utc_now(), cluster_id),
        )

        # 清空簇成员
        conn.execute(
            "DELETE FROM memory_cluster_members WHERE cluster_id = ?", (cluster_id,)
        )

        # 新记忆加入新簇
        new_cluster_id = f"cluster_{uuid.uuid4().hex[:12]}"
        conn.execute(
            "INSERT INTO memory_clusters (cluster_id, key, created_at, status) VALUES (?, ?, ?, 'active')",
            (new_cluster_id, key, get_utc_now()),
        )
        conn.execute(
            "INSERT INTO memory_cluster_members (cluster_id, fingerprint, added_at) VALUES (?, ?, ?)",
            (new_cluster_id, merged_fingerprint, get_utc_now()),
        )

        conn.commit()

        return {
            "success": True,
            "old_fingerprints": old_fps,
            "new_fingerprint": merged_fingerprint,
            "new_cluster_id": new_cluster_id,
            "edges_redirected": len(edge_map_out) + len(edge_map_in),
        }

    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def get_cluster_info(cluster_id: str) -> dict:
    """获取簇信息（用于 LLM 合并）"""
    conn = get_db()
    try:
        cluster = conn.execute(
            "SELECT * FROM memory_clusters WHERE cluster_id = ?",
            (cluster_id,),
        ).fetchone()

        if not cluster:
            return {"success": False, "error": "Cluster not found"}

        members = conn.execute(
            """
            SELECT m.fingerprint, m.memory, m.tag, m.created_at
            FROM memory_cluster_members mcm
            JOIN memory m ON mcm.fingerprint = m.fingerprint
            WHERE mcm.cluster_id = ?
            ORDER BY m.created_at ASC
            """,
            (cluster_id,),
        ).fetchall()

        return {
            "success": True,
            "cluster": dict(cluster),
            "members": [dict(row) for row in members],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

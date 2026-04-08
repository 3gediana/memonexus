"""
记忆价值评估器 - 多维度计算记忆价值

数学模型来源：
- PageRank: Brin & Page (1998), "The Anatomy of a Large-Scale Hypertextual Web Search Engine"
- ACT-R: Anderson (1993), "Rules of the Mind"
"""

import math
from src.tools.memory_tools import get_db
from src.system.logger import get_module_logger
from src.system.config import load_config

logger = get_module_logger("value_assessor")

# PageRank + ACT-R 模型参数
W_PAGERANK = 0.4
W_ACTR = 0.35
W_BASE = 0.15
W_SEMANTIC = 0.1

PR_DAMPING = 0.85
PR_ITERATIONS = 20
PR_MIN_VALUE = 0.15

VALUE_PRUNE_THRESHOLD = 0.12
MEMORY_COUNT_THRESHOLD = 500

SEMANTIC_COEFFICIENTS = {
    "valid": 1.0,
    "completed": 0.5,
    "expired": 0.1,
}


class ValueAssessor:
    """记忆价值评估器"""

    def __init__(self):
        self._pagerank_cache = {}
        # 旧版 hit_rate 模型权重（保留用于向后兼容）
        self.hit_rate_weight = 0.4
        self.edge_richness_weight = 0.2
        self.edge_quality_weight = 0.2
        self.direct_recall_rate_weight = 0.2

    # ========== PageRank + ACT-R 模型（新版） ==========

    def compute_pagerank(self) -> dict:
        """
        计算所有记忆的 PageRank 值

        公式：PR(A) = (1-d)/N + d * Σ(PR(Ti)/C(Ti))
        处理悬挂节点：将质量均匀分配给所有节点
        """
        conn = get_db()
        try:
            all_fps = conn.execute("SELECT fingerprint FROM memory").fetchall()
            all_fps = [row["fingerprint"] for row in all_fps]
            n = len(all_fps)

            if n == 0:
                return {"success": True, "pagerank": {}}

            fp_set = set(all_fps)
            pagerank = {fp: 1.0 / n for fp in all_fps}

            out_edges = {}
            in_edges = {fp: [] for fp in all_fps}

            edge_rows = conn.execute(
                "SELECT from_fingerprint, to_fingerprint, effective_strength FROM edges"
            ).fetchall()

            for row in edge_rows:
                src = row["from_fingerprint"]
                dst = row["to_fingerprint"]
                strength = row["effective_strength"] or row.get("strength", 0.5)

                if src not in out_edges:
                    out_edges[src] = []
                out_edges[src].append((dst, strength))

                if dst in fp_set:
                    in_edges[dst].append((src, strength))

            for iteration in range(PR_ITERATIONS):
                dangling_mass = 0.0
                for fp in all_fps:
                    src_out = out_edges.get(fp, [])
                    src_out_degree = sum(s for _, s in src_out)
                    if src_out_degree == 0:
                        dangling_mass += pagerank[fp]

                dangling_share = dangling_mass / n

                new_pagerank = {}
                for fp in all_fps:
                    rank_sum = 0.0
                    for src, strength in in_edges[fp]:
                        src_out = out_edges.get(src, [])
                        src_out_degree = sum(s for _, s in src_out)
                        if src_out_degree > 0:
                            rank_sum += pagerank[src] * (strength / src_out_degree)

                    new_pagerank[fp] = (1 - PR_DAMPING) / n + PR_DAMPING * (
                        rank_sum + dangling_share
                    )

                pagerank = new_pagerank

            max_pr = max(pagerank.values()) if pagerank else 1.0
            if max_pr == 0:
                max_pr = 1.0

            normalized = {
                fp: max(pr / max_pr, PR_MIN_VALUE) for fp, pr in pagerank.items()
            }

            self._pagerank_cache = normalized

            return {"success": True, "pagerank": normalized}

        except Exception as e:
            logger.error(f"PageRank 计算失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def compute_actr(self, fingerprint: str, max_recall: int = None) -> float:
        """
        计算单条记忆的 ACT-R 激活值

        公式：A = ln(recall_count + 1) / ln(max_recall + 1)
        归一化到 [0, 1]
        """
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT recall_count FROM memory WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()

            if not row:
                return 0.0

            recall_count = row["recall_count"] or 0

            if max_recall is None:
                max_row = conn.execute(
                    "SELECT MAX(recall_count) as max_recall FROM memory"
                ).fetchone()
                max_recall = max_row["max_recall"] or 1

            if max_recall == 0:
                max_recall = 1

            if recall_count == 0:
                return 0.0

            actr = math.log(recall_count + 1) / math.log(max_recall + 1)
            return min(max(actr, 0.0), 1.0)

        except Exception:
            return 0.0
        finally:
            conn.close()

    def get_semantic_coefficient(self, fingerprint: str) -> float:
        """获取语义状态系数"""
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT semantic_status FROM memory WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()

            if not row:
                return 1.0

            status = row["semantic_status"] or "valid"
            return SEMANTIC_COEFFICIENTS.get(status, 1.0)

        except Exception:
            return 1.0
        finally:
            conn.close()

    def calculate_value(self, fingerprint: str) -> dict:
        """
        计算单条记忆的综合价值（PageRank + ACT-R 模型）

        V = w1*PageRank + w2*ACT-R + w3*BaseScore + w4*SemanticFreshness
        """
        try:
            conn = get_db()
            row = conn.execute(
                "SELECT base_score, recall_count, semantic_status FROM memory WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            conn.close()

            if not row:
                return {"success": False, "error": "FP_NOT_FOUND"}

            base_score = row["base_score"] or 0.5

            pagerank_value = self._pagerank_cache.get(fingerprint, 0.5)
            actr_value = self.compute_actr(fingerprint)
            semantic_coeff = self.get_semantic_coefficient(fingerprint)

            value = (
                W_PAGERANK * pagerank_value
                + W_ACTR * actr_value
                + W_BASE * base_score
                + W_SEMANTIC * semantic_coeff
            )

            value = min(max(value, 0.0), 1.0)

            conn = get_db()
            conn.execute(
                "UPDATE memory SET value_score = ? WHERE fingerprint = ?",
                (value, fingerprint),
            )
            conn.commit()
            conn.close()

            return {
                "success": True,
                "value": value,
                "components": {
                    "pagerank": round(pagerank_value, 4),
                    "actr": round(actr_value, 4),
                    "base_score": round(base_score, 4),
                    "semantic_coeff": round(semantic_coeff, 4),
                },
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def update_all_values(self) -> dict:
        """批量重算所有记忆的价值"""
        pr_result = self.compute_pagerank()
        if not pr_result["success"]:
            return pr_result

        conn = get_db()
        try:
            all_fps = conn.execute(
                "SELECT fingerprint, recall_count, base_score, semantic_status FROM memory"
            ).fetchall()

            max_recall = max((row["recall_count"] or 0 for row in all_fps), default=1)
            if max_recall == 0:
                max_recall = 1

            update_pairs = []
            for row in all_fps:
                fp = row["fingerprint"]
                recall_count = row["recall_count"] or 0
                base_score = row["base_score"] or 0.5
                status = row["semantic_status"] or "valid"
                semantic_coeff = SEMANTIC_COEFFICIENTS.get(status, 1.0)

                pagerank_value = self._pagerank_cache.get(fp, 0.5)

                if recall_count == 0:
                    actr_value = 0.0
                else:
                    actr_value = math.log(recall_count + 1) / math.log(max_recall + 1)
                    actr_value = min(max(actr_value, 0.0), 1.0)

                value = (
                    W_PAGERANK * pagerank_value
                    + W_ACTR * actr_value
                    + W_BASE * base_score
                    + W_SEMANTIC * semantic_coeff
                )
                value = min(max(value, 0.0), 1.0)
                update_pairs.append((value, fp))

            conn.executemany(
                "UPDATE memory SET value_score = ? WHERE fingerprint = ?",
                update_pairs,
            )
            conn.commit()

            return {"success": True, "updated": len(update_pairs)}

        except Exception as e:
            logger.error(f"批量价值更新失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    # ========== 旧版 hit_rate 模型（保留向后兼容） ==========

    def calculate_value_legacy(self, fingerprint: str) -> dict:
        """
        计算单条记忆的价值（旧版 hit_rate + edge_richness 模型）
        保留用于向后兼容和对比分析
        """
        try:
            conn = get_db()

            memory_row = conn.execute(
                "SELECT recall_count, hit_count, direct_recall_count, total_recall_count FROM memory WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()

            if not memory_row:
                conn.close()
                return {"success": False, "error": "FP_NOT_FOUND"}

            recall_count = memory_row["recall_count"] or 0
            hit_count = memory_row["hit_count"] or 0
            direct_recall_count = memory_row["direct_recall_count"] or 0
            total_recall_count = memory_row["total_recall_count"] or 0

            edge_rows = conn.execute(
                "SELECT effective_strength FROM edges WHERE from_fingerprint = ? OR to_fingerprint = ?",
                (fingerprint, fingerprint),
            ).fetchall()
            conn.close()

            edge_count = len(edge_rows)
            if edge_count > 0:
                edge_quality = (
                    sum(e["effective_strength"] or 0.5 for e in edge_rows) / edge_count
                )
            else:
                edge_quality = 0.0

            hit_rate = hit_count / max(recall_count, 1)
            edge_richness = min(edge_count / 10, 1.0)
            direct_recall_rate = direct_recall_count / max(total_recall_count, 1)

            value = (
                hit_rate * self.hit_rate_weight
                + edge_richness * self.edge_richness_weight
                + edge_quality * self.edge_quality_weight
                + direct_recall_rate * self.direct_recall_rate_weight
            )

            return {
                "success": True,
                "fingerprint": fingerprint,
                "value": round(value, 3),
                "details": {
                    "hit_rate": round(hit_rate, 3),
                    "edge_richness": round(edge_richness, 3),
                    "edge_quality": round(edge_quality, 3),
                    "direct_recall_rate": round(direct_recall_rate, 3),
                    "edge_count": edge_count,
                    "recall_count": recall_count,
                    "hit_count": hit_count,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def calculate_batch(self, fingerprints: list) -> dict:
        """批量计算记忆价值（使用新版模型）"""
        results = []
        for fp in fingerprints:
            result = self.calculate_value(fp)
            if result["success"]:
                results.append(result)

        results.sort(key=lambda x: x["value"], reverse=True)

        return {"success": True, "results": results}

    def get_top_valuable(self, key: str, topk: int = 10) -> dict:
        """获取指定key下最有价值的记忆"""
        try:
            conn = get_db()
            rows = conn.execute(
                "SELECT fingerprint, tag FROM memory WHERE key = ?",
                (key,),
            ).fetchall()
            conn.close()

            fingerprints = [row["fingerprint"] for row in rows]
            batch_result = self.calculate_batch(fingerprints)

            if not batch_result["success"]:
                return batch_result

            fp_to_tag = {row["fingerprint"]: row["tag"] for row in rows}
            memories = []
            for item in batch_result["results"][:topk]:
                memories.append(
                    {
                        "fingerprint": item["fingerprint"],
                        "value": item["value"],
                        "tag": fp_to_tag.get(item["fingerprint"], ""),
                        "details": item.get("components", {}),
                    }
                )

            return {"success": True, "memories": memories}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ========== 淘汰逻辑 ==========

    def prune_low_value_memories(self, threshold: float = None) -> dict:
        """
        淘汰低价值记忆

        淘汰条件（满足任一即可）：
        1. value_score < threshold 且 recall_count < 平均召回次数的配置比例
        2. semantic_status = 'expired' 且 value_score < 0.3
        """
        if threshold is None:
            threshold = VALUE_PRUNE_THRESHOLD

        conn = get_db()
        try:
            total_count = conn.execute("SELECT COUNT(*) as cnt FROM memory").fetchone()[
                "cnt"
            ]

            if total_count < MEMORY_COUNT_THRESHOLD:
                return {"success": True, "pruned": 0, "reason": "Below threshold"}

            avg_recall_row = conn.execute(
                "SELECT AVG(recall_count) as avg_recall FROM memory"
            ).fetchone()
            avg_recall = avg_recall_row["avg_recall"] or 0
            config = load_config()
            recall_ratio = config.get("prune_recall_ratio", 0.001)
            recall_threshold = avg_recall * recall_ratio

            candidates = conn.execute(
                """SELECT fingerprint, value_score, recall_count, semantic_status, base_score
                   FROM memory
                   WHERE (value_score < ? AND recall_count < ?)
                      OR (semantic_status = 'expired' AND value_score < 0.3)""",
                (threshold, recall_threshold),
            ).fetchall()

            if not candidates:
                return {
                    "success": True,
                    "pruned": 0,
                    "reason": "No candidates met criteria",
                }

            pagerank_cache = self._pagerank_cache or {}
            to_prune = []
            for row in candidates:
                fp = row["fingerprint"]
                pr_value = pagerank_cache.get(fp, 0.5)
                if pr_value < 0.3:
                    to_prune.append(fp)

            if not to_prune:
                return {
                    "success": True,
                    "pruned": 0,
                    "reason": "No candidates with low PageRank",
                }

            placeholders = ",".join("?" for _ in to_prune)
            conn.execute(
                f"DELETE FROM edges WHERE from_fingerprint IN ({placeholders}) OR to_fingerprint IN ({placeholders})",
                to_prune + to_prune,
            )

            # Clean up orphaned clusters BEFORE deleting memories:
            # find clusters whose ALL members are in the to_prune list
            orphaned_cluster_ids = conn.execute(
                f"""SELECT cluster_id FROM memory_cluster_members
                    GROUP BY cluster_id
                    HAVING COUNT(*) = SUM(CASE WHEN fingerprint IN ({placeholders}) THEN 1 ELSE 0 END)""",
                to_prune,
            ).fetchall()
            for cid_row in orphaned_cluster_ids:
                conn.execute(
                    "DELETE FROM memory_cluster_members WHERE cluster_id = ?",
                    (cid_row["cluster_id"],),
                )
                conn.execute(
                    "DELETE FROM memory_clusters WHERE cluster_id = ?",
                    (cid_row["cluster_id"],),
                )

            conn.execute(
                f"DELETE FROM memory_cluster_members WHERE fingerprint IN ({placeholders})",
                to_prune,
            )

            conn.execute(
                f"DELETE FROM memory WHERE fingerprint IN ({placeholders})",
                to_prune,
            )
            conn.commit()

            for fp in to_prune:
                self._pagerank_cache.pop(fp, None)

            return {
                "success": True,
                "pruned": len(to_prune),
                "fingerprints": to_prune,
                "avg_recall": round(avg_recall, 2),
            }

        except Exception as e:
            logger.error(f"淘汰失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def get_memory_count(self) -> int:
        """获取当前记忆总数"""
        conn = get_db()
        try:
            row = conn.execute("SELECT COUNT(*) as cnt FROM memory").fetchone()
            return row["cnt"]
        except Exception:
            return 0
        finally:
            conn.close()

    def increment_recall_count(self, fingerprint: str) -> dict:
        """增加记忆的召回次数"""
        conn = get_db()
        try:
            conn.execute(
                "UPDATE memory SET recall_count = recall_count + 1 WHERE fingerprint = ?",
                (fingerprint,),
            )
            conn.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()

    def update_semantic_status(self, fingerprint: str, status: str) -> dict:
        """更新记忆的语义状态"""
        if status not in SEMANTIC_COEFFICIENTS:
            return {"success": False, "error": f"Invalid status: {status}"}

        conn = get_db()
        try:
            conn.execute(
                "UPDATE memory SET semantic_status = ? WHERE fingerprint = ?",
                (status, fingerprint),
            )
            conn.commit()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            conn.close()


_assessor_instance = None


def get_value_assessor() -> ValueAssessor:
    global _assessor_instance
    if _assessor_instance is None:
        _assessor_instance = ValueAssessor()
    return _assessor_instance

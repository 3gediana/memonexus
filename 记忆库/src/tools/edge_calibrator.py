"""
边强度校准器 - 根据命中率校准effective_strength

核心公式：
  if recall_count < 9:
      calibration = 1.0  # 样本少，信任预判
  else:
      calibration = hit_count / recall_count  # 用命中率校准

  effective = (1 - beta) × prev + beta × (strength × calibration)
  effective = max(effective, strength × 0.3)  # 弹性地板
"""

from src.tools.memory_tools import get_db
from src.system.config import get_current_instance_config
from src.system.logger import get_module_logger

logger = get_module_logger("calibrator")


BETA = 0.2
CONFIDENCE_THRESHOLD = 9
FLOOR_RATIO = 0.3


class EdgeStrengthCalibrator:
    """边强度校准器"""

    def record_recall(self, from_fp: str, to_fp: str) -> dict:
        """记录一次边被召回并校准effective_strength"""
        logger.debug(f"记录召回: {from_fp[:8]}... -> {to_fp[:8]}...")
        try:
            conn = get_db()
            try:
                conn.execute(
                    "UPDATE edges SET recall_count = recall_count + 1 WHERE from_fingerprint = ? AND to_fingerprint = ?",
                    (from_fp, to_fp),
                )
                conn.commit()
                # 自动校准
                self.calibrate(from_fp, to_fp)
                return {"success": True}
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"记录召回失败: {e}")
            return {"success": False, "error": str(e)}

    def record_hit(self, from_fp: str, to_fp: str) -> dict:
        """记录一次边命中并校准effective_strength"""
        try:
            conn = get_db()
            try:
                conn.execute(
                    "UPDATE edges SET hit_count = hit_count + 1 WHERE from_fingerprint = ? AND to_fingerprint = ?",
                    (from_fp, to_fp),
                )
                conn.commit()
                # 自动校准
                self.calibrate(from_fp, to_fp)
                return {"success": True}
            finally:
                conn.close()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def calibrate(self, from_fp: str, to_fp: str) -> dict:
        """计算并更新单条边的effective_strength"""
        try:
            conn = get_db()
            try:
                row = conn.execute(
                    "SELECT strength, recall_count, hit_count, effective_strength FROM edges WHERE from_fingerprint = ? AND to_fingerprint = ?",
                    (from_fp, to_fp),
                ).fetchone()

                if not row:
                    return {"success": False, "error": "EDGE_NOT_FOUND"}

                strength = row["strength"]
                recall_count = row["recall_count"] or 0
                hit_count = row["hit_count"] or 0
                prev_effective = row["effective_strength"] or strength

                new_effective = self._compute(
                    strength, recall_count, hit_count, prev_effective
                )

                conn.execute(
                    "UPDATE edges SET effective_strength = ? WHERE from_fingerprint = ? AND to_fingerprint = ?",
                    (new_effective, from_fp, to_fp),
                )
                conn.commit()

                return {
                    "success": True,
                    "from": from_fp,
                    "to": to_fp,
                    "effective_strength": new_effective,
                }
            finally:
                conn.close()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def calibrate_all(self) -> dict:
        """批量校准所有边"""
        try:
            conn = get_db()
            try:
                rows = conn.execute(
                    "SELECT from_fingerprint, to_fingerprint, strength, recall_count, hit_count, effective_strength FROM edges"
                ).fetchall()

                updated = 0
                for row in rows:
                    strength = row["strength"]
                    recall_count = row["recall_count"] or 0
                    hit_count = row["hit_count"] or 0
                    prev_effective = row["effective_strength"] or strength

                    new_effective = self._compute(
                        strength, recall_count, hit_count, prev_effective
                    )

                    if abs(new_effective - prev_effective) > 0.001:
                        conn.execute(
                            "UPDATE edges SET effective_strength = ? WHERE from_fingerprint = ? AND to_fingerprint = ?",
                            (
                                new_effective,
                                row["from_fingerprint"],
                                row["to_fingerprint"],
                            ),
                        )
                        updated += 1

                conn.commit()

                # 清空 PageRank 缓存并标记聚类需要重建
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

                return {"success": True, "updated": updated, "total": len(rows)}
            finally:
                conn.close()
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def _compute(
        strength: float, recall_count: int, hit_count: int, prev_effective: float
    ) -> float:
        """计算effective_strength"""
        if recall_count < CONFIDENCE_THRESHOLD:
            calibration = 1.0
        else:
            calibration = hit_count / recall_count

        new_effective = (1 - BETA) * prev_effective + BETA * (strength * calibration)

        # 弹性地板：不低于strength的30%
        floor = strength * FLOOR_RATIO
        # 弹性天花板：不超过strength
        ceiling = strength
        return max(floor, min(new_effective, ceiling))


_calibrator_instance = None


def get_calibrator() -> EdgeStrengthCalibrator:
    """获取校准器实例（单例）"""
    global _calibrator_instance
    if _calibrator_instance is None:
        _calibrator_instance = EdgeStrengthCalibrator()
    return _calibrator_instance

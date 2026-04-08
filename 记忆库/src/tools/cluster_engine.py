"""
聚类引擎 - 使用Louvain算法发现记忆社区
"""

import json
import os
from collections import defaultdict
from src.tools.memory_tools import get_db
from src.system.config import get_current_instance_config

try:
    import community as community_louvain
    import networkx as nx

    LOUVAIN_AVAILABLE = True
except ImportError:
    LOUVAIN_AVAILABLE = False


class ClusterEngine:
    """记忆聚类引擎"""

    REBUILD_THRESHOLD = 50  # 累计50次变化才重建

    def __init__(self):
        self._clusters = None
        self._fingerprint_to_cluster = None
        self._change_counter = 0  # 变化计数器
        self._dirty = False

    def get_clusters_file_path(self) -> str:
        """获取聚类结果文件路径"""
        instance = get_current_instance_config()
        data_dir = os.path.dirname(instance["db_path"])
        return os.path.join(data_dir, "clusters.json")

    def _current_instance_key(self) -> str:
        from src.system.config import get_current_instance_config
        return get_current_instance_config()["db_path"]

    def load_clusters(self) -> dict:
        """加载聚类结果"""
        cached = getattr(self, '_instance_key', None)
        current = self._current_instance_key()
        if cached is not None and cached != current:
            self._clusters = None
            self._fingerprint_to_cluster = None

        if self._clusters is not None:
            return self._clusters

        clusters_file = self.get_clusters_file_path()
        if not os.path.exists(clusters_file):
            self._clusters = {}
            self._fingerprint_to_cluster = {}
            return self._clusters

        try:
            with open(clusters_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._clusters = data.get("clusters", {})
                self._fingerprint_to_cluster = data.get("fingerprint_to_cluster", {})
            self._instance_key = current
            return self._clusters
        except:
            self._clusters = {}
            self._fingerprint_to_cluster = {}
            self._instance_key = current
            return self._clusters

    def mark_changed(self):
        """标记聚类需要重建，达到阈值时触发"""
        self._change_counter += 1
        self._dirty = True
        if self._change_counter >= self.REBUILD_THRESHOLD:
            self.build_clusters()
            self._change_counter = 0
            self._dirty = False

    def get_change_counter(self) -> int:
        """获取变化计数器"""
        return self._change_counter

    def save_clusters(self, clusters: dict, fp_to_cluster: dict) -> dict:
        """保存聚类结果"""
        try:
            clusters_file = self.get_clusters_file_path()
            os.makedirs(os.path.dirname(clusters_file), exist_ok=True)

            data = {
                "clusters": clusters,
                "fingerprint_to_cluster": fp_to_cluster,
            }

            with open(clusters_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self._clusters = clusters
            self._fingerprint_to_cluster = fp_to_cluster
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_clustering(self) -> dict:
        """
        执行聚类

        Returns:
            {"success": bool, "cluster_count": int, "memory_count": int}
        """
        if not LOUVAIN_AVAILABLE:
            return {"success": False, "error": "python-louvain not installed"}

        try:
            # 读取edges
            conn = get_db()
            edges = conn.execute(
                "SELECT from_fingerprint, to_fingerprint, effective_strength FROM edges"
            ).fetchall()
            conn.close()

            # 检查edges数量
            if len(edges) < 10:
                return {
                    "success": True,
                    "cluster_count": 0,
                    "memory_count": 0,
                    "skipped": True,
                    "reason": "edges < 10",
                }

            # 构建图
            G = nx.Graph()
            for edge in edges:
                G.add_edge(
                    edge["from_fingerprint"],
                    edge["to_fingerprint"],
                    weight=edge["effective_strength"] or 0.5,
                )

            # 执行Louvain聚类
            partition = community_louvain.best_partition(G, weight="weight")

            # 整理结果
            clusters = defaultdict(list)
            for fp, cluster_id in partition.items():
                clusters[str(cluster_id)].append(fp)

            # 转换为普通dict
            clusters = dict(clusters)
            fp_to_cluster = {fp: str(cid) for fp, cid in partition.items()}

            # 保存结果
            save_result = self.save_clusters(clusters, fp_to_cluster)
            if not save_result["success"]:
                return save_result

            return {
                "success": True,
                "cluster_count": len(clusters),
                "memory_count": len(partition),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_cluster_id(self, fingerprint: str) -> str:
        """获取记忆所在的社区ID"""
        self.load_clusters()
        return self._fingerprint_to_cluster.get(fingerprint)

    def are_same_cluster(self, fp1: str, fp2: str) -> bool:
        """判断两个记忆是否在同一社区"""
        cluster1 = self.get_cluster_id(fp1)
        cluster2 = self.get_cluster_id(fp2)
        if cluster1 is None or cluster2 is None:
            return False
        return cluster1 == cluster2

    def get_cluster_score_bonus(self, fp1: str, fp2: str) -> float:
        """获取同社区的分数加成"""
        if self.are_same_cluster(fp1, fp2):
            return 0.2
        return 0.0

    def get_cluster_memories(self, cluster_id: str) -> list:
        """获取指定社区的所有记忆"""
        self.load_clusters()
        return self._clusters.get(cluster_id, [])

    def get_stats(self) -> dict:
        """获取聚类统计信息"""
        self.load_clusters()
        return {
            "cluster_count": len(self._clusters),
            "memory_count": len(self._fingerprint_to_cluster),
        }


_engine_instance = None


def get_cluster_engine() -> ClusterEngine:
    """获取聚类引擎实例"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ClusterEngine()
    return _engine_instance

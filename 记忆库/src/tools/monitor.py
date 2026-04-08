"""
System Monitor - View runtime status
"""

import json
from src.tools.memory_tools import get_db
from src.system.config import get_current_instance_config
from src.tools.cluster_engine import get_cluster_engine
from src.tools.preference_tracker import get_preference_tracker


class SystemMonitor:
    """System Monitor"""

    def get_memory_stats(self) -> dict:
        """Get memory statistics"""
        try:
            conn = get_db()

            # Total count
            total = conn.execute("SELECT COUNT(*) as count FROM memory").fetchone()[
                "count"
            ]

            # By key
            key_stats = conn.execute(
                "SELECT key, COUNT(*) as count FROM memory GROUP BY key ORDER BY count DESC"
            ).fetchall()

            # Recent 7 days
            recent = conn.execute("""
                SELECT COUNT(*) as count FROM memory 
                WHERE created_at >= datetime('now', '-7 days')
            """).fetchone()["count"]

            conn.close()

            return {
                "total": total,
                "by_key": {row["key"]: row["count"] for row in key_stats},
                "recent_7days": recent,
            }
        except Exception as e:
            return {"error": str(e)}

    def get_edge_stats(self) -> dict:
        """Get edge statistics"""
        try:
            conn = get_db()

            # Total count
            total = conn.execute("SELECT COUNT(*) as count FROM edges").fetchone()[
                "count"
            ]

            # Strength distribution
            strength_stats = conn.execute("""
                SELECT 
                    CASE 
                        WHEN strength >= 0.9 THEN 'strong'
                        WHEN strength >= 0.6 THEN 'medium'
                        ELSE 'weak'
                    END as strength_level,
                    COUNT(*) as count
                FROM edges 
                GROUP BY strength_level
            """).fetchall()

            # Average strength
            avg_strength = (
                conn.execute("SELECT AVG(strength) as avg FROM edges").fetchone()["avg"]
                or 0
            )

            conn.close()

            return {
                "total": total,
                "by_strength": {
                    row["strength_level"]: row["count"] for row in strength_stats
                },
                "avg_strength": round(avg_strength, 3),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_cluster_stats(self) -> dict:
        """Get cluster statistics"""
        engine = get_cluster_engine()
        return engine.get_stats()

    def get_preference_stats(self) -> dict:
        """Get preference statistics"""
        tracker = get_preference_tracker()
        return tracker.get_stats()

    def get_sub_stats(self) -> dict:
        """Get conversation log statistics"""
        try:
            from src.db.init import get_current_db_paths
            import sqlite3

            paths = get_current_db_paths()
            conn = sqlite3.connect(paths["sub_db_path"])
            conn.row_factory = sqlite3.Row

            total = conn.execute("SELECT COUNT(*) as count FROM sub").fetchone()[
                "count"
            ]

            # Recent 7 days
            recent = conn.execute("""
                SELECT COUNT(*) as count FROM sub 
                WHERE created_at >= datetime('now', '-7 days')
            """).fetchone()["count"]

            conn.close()

            return {"total": total, "recent_7days": recent}
        except Exception as e:
            return {"error": str(e)}

    def get_full_report(self) -> dict:
        """Get full report"""
        instance = get_current_instance_config()

        return {
            "instance": instance.get("name", "unknown"),
            "memory": self.get_memory_stats(),
            "edge": self.get_edge_stats(),
            "cluster": self.get_cluster_stats(),
            "preference": self.get_preference_stats(),
            "sub": self.get_sub_stats(),
        }

    def print_report(self):
        """Print report"""
        report = self.get_full_report()

        print("=" * 50)
        print(f"  System Monitor - Instance: {report['instance']}")
        print("=" * 50)

        # Memory
        memory = report["memory"]
        print(f"\n[Memory]")
        print(f"  Total: {memory.get('total', 0)}")
        print(f"  Recent 7 days: {memory.get('recent_7days', 0)}")
        if "by_key" in memory:
            print(f"  By Key:")
            for key, count in list(memory["by_key"].items())[:10]:
                print(f"    - {key}: {count}")

        # Edge
        edge = report["edge"]
        print(f"\n[Edge]")
        print(f"  Total: {edge.get('total', 0)}")
        print(f"  Avg Strength: {edge.get('avg_strength', 0)}")
        if "by_strength" in edge:
            print(f"  Strength Distribution:")
            for level, count in edge["by_strength"].items():
                print(f"    - {level}: {count}")

        # Cluster
        cluster = report["cluster"]
        print(f"\n[Cluster]")
        print(f"  Communities: {cluster.get('cluster_count', 0)}")
        print(f"  Clustered Memories: {cluster.get('memory_count', 0)}")

        # Preference
        preference = report["preference"]
        print(f"\n[Preference]")
        print(f"  Total Calls: {preference.get('total_calls', 0)}")
        if "keys" in preference:
            print(f"  Top Keys:")
            for key, count in list(preference["keys"].items())[:5]:
                print(f"    - {key}: {count}")

        # Sub
        sub = report["sub"]
        print(f"\n[Conversation Log]")
        print(f"  Total: {sub.get('total', 0)}")
        print(f"  Recent 7 days: {sub.get('recent_7days', 0)}")

        print("\n" + "=" * 50)


# Global instance
_monitor_instance = None


def get_monitor() -> SystemMonitor:
    """Get monitor instance"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = SystemMonitor()
    return _monitor_instance

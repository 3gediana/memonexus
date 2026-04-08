"""
演示编排器 - 驱动 SimUser Agent 与 Memory System 交互，记录全链路日志
"""

import json
import os
import time
import sys
import io
from datetime import datetime

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.demo.sim_user import SimUserAgent
from src.demo.demo_tools import DemoTools
from src.tools.key_tools import get_key_overview
from src.tools.memory_tools import get_db
from src.tools.cluster_engine import get_cluster_engine
from src.tools.edge_tools import list_edges_by_fingerprint
from src.system.debug import set_debug_mode, DEBUG_MODE
from src.system.main import handle_user_message
from src.system.storage_flow import process_user_message


class DemoOrchestrator:
    def __init__(self, log_dir: str = "demo_logs"):
        self.sim_user = SimUserAgent()
        self.demo_tools = DemoTools(log_callback=self._on_tool_result)
        self.log_dir = log_dir
        self.log_file = None
        self.round = 0
        self.max_rounds = 35
        self.conversation_history = []
        self.tool_logs = []  # 当前轮次的工具调用日志
        self.start_time = None

    def run(self):
        """执行完整演示流程"""
        os.makedirs(self.log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(self.log_dir, f"demo_{timestamp}.jsonl")

        self.start_time = time.time()
        self._print_header()

        with open(self.log_file, "w", encoding="utf-8") as f:
            self._write_log(
                f, {"event": "demo_start", "timestamp": datetime.now().isoformat()}
            )

            while self.round < self.max_rounds:
                self.round += 1
                self.tool_logs = []

                # 1. SimUser 决定下一步
                self._print_phase("决策", f"Round {self.round}")
                decision = self.sim_user.decide_next()

                action = decision.get("action")
                args = decision.get("args", {})
                thought = decision.get("thought", "")

                if not action or action == "none":
                    self._print_warning("SimUser 未做出决策，跳过本轮")
                    continue

                self._print_info(
                    f"SimUser 决定: {action}({json.dumps(args, ensure_ascii=False)})"
                )

                # 2. 检查是否结束
                if action == "finish_demo":
                    self._print_success("演示结束")
                    self._write_log(
                        f,
                        {
                            "event": "demo_end",
                            "round": self.round,
                            "sim_user_status": self.sim_user.get_status(),
                        },
                    )

                    # 清理演示产生的垃圾
                    self._print_phase("清理", "删除演示实例和临时数据")
                    cleanup_result = self.demo_tools.cleanup_demo("student_life")
                    if cleanup_result.get("success"):
                        for item in cleanup_result.get("cleaned", []):
                            print(f"  ✓ {item}")
                    break

                # 3. 执行工具
                self._print_phase("执行", action)
                result = self.demo_tools.execute(action, args)

                # 4. 记录对话历史
                if action == "chat":
                    self.conversation_history.append(
                        {
                            "role": "user",
                            "content": args.get("message", ""),
                        }
                    )
                    if result.get("success"):
                        reply = result.get("reply", "")
                        self.conversation_history.append(
                            {
                                "role": "assistant",
                                "content": reply[:500],
                            }
                        )
                        self._print_reply(reply)

                elif action == "new_session":
                    self.conversation_history = []
                    self.demo_tools.turn_index = 0

                # 5. 通知 SimUser 观察结果
                self.sim_user.observe_result(action, args, result)

                # 6. 写日志
                self._write_log(
                    f,
                    {
                        "event": "round",
                        "round": self.round,
                        "timestamp": datetime.now().isoformat(),
                        "sim_user": {
                            "thought": thought,
                            "action": action,
                            "args": args,
                            "revealed_info": self.sim_user.agent_memory.get(
                                "revealed_info", []
                            ),
                        },
                        "tool_result": result,
                        "tool_calls": self.tool_logs,
                        "db_snapshot": self._get_db_snapshot(),
                    },
                )

                # 7. 节奏控制
                time.sleep(2)

        # 最终报告
        self._print_final_report()

    def _on_tool_result(self, tool_name: str, params: dict, result: dict):
        """工具调用回调，记录到当前轮次日志"""
        self.tool_logs.append(
            {
                "tool": tool_name,
                "params": params,
                "result": result,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def _write_log(self, f, data: dict):
        """写入一行日志"""
        f.write(json.dumps(data, ensure_ascii=False) + "\n")
        f.flush()

    def _get_db_snapshot(self) -> dict:
        """获取当前数据库快照"""
        try:
            overview = get_key_overview(include_summary=False)
            total_memories = 0
            key_dist = {}
            if overview.get("success"):
                for k in overview.get("keys", []):
                    count = k.get("memory_count", 0)
                    total_memories += count
                    if count > 0:
                        key_dist[k["key"]] = count

            conn = get_db()
            edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            conn.close()

            engine = get_cluster_engine()
            cluster_stats = engine.get_stats()

            return {
                "total_memories": total_memories,
                "total_edges": edge_count,
                "key_distribution": key_dist,
                "clusters": cluster_stats.get("cluster_count", 0),
            }
        except Exception as e:
            return {"error": str(e)}

    def _print_header(self):
        print("\n" + "=" * 70)
        print("  Memory Assistant - 全流程演示")
        print(f"  开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  日志文件: {self.log_file}")
        print("=" * 70 + "\n")

    def _print_phase(self, phase: str, detail: str):
        print(f"\n{'─' * 70}")
        print(f"  [{phase}] {detail}")
        print(f"{'─' * 70}")

    def _print_info(self, msg: str):
        print(f"  [INFO] {msg}")

    def _print_warning(self, msg: str):
        print(f"  [WARN] {msg}")

    def _print_success(self, msg: str):
        print(f"  [OK] {msg}")

    def _print_reply(self, reply: str):
        import re

        # 过滤 emoji
        reply_clean = re.sub(
            r"[^\u0020-\u007E\u4E00-\u9FFF\u3000-\u303F\uff00-\uffef]", "", reply
        )
        preview = reply_clean[:200] + "..." if len(reply_clean) > 200 else reply_clean
        print(f"\n  [AI回复] {preview}\n")

    def _print_final_report(self):
        elapsed = time.time() - self.start_time
        status = self.sim_user.get_status()

        print("\n" + "=" * 70)
        print("  演示完成 - 最终报告")
        print("=" * 70)
        print(f"  总轮次: {self.round}")
        print(f"  耗时: {elapsed:.1f} 秒")
        print(f"  透露信息类别: {', '.join(status['agent_memory']['revealed_info'])}")
        print(f"  日志文件: {self.log_file}")

        db = self._get_db_snapshot()
        print(f"\n  数据库状态:")
        print(f"    总记忆数: {db.get('total_memories', 0)}")
        print(f"    总边数: {db.get('total_edges', 0)}")
        print(f"    聚类数: {db.get('clusters', 0)}")
        if db.get("key_distribution"):
            print(f"    分布:")
            for k, v in db["key_distribution"].items():
                print(f"      {k}: {v}")
        print("=" * 70 + "\n")

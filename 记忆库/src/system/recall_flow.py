import time
import json
from src.tools.recall_tools import dispatch_recall_to_keys, request_memory_recall
from src.tools.query_tools import get_memory_by_fingerprint as get_memory_by_fp_list
from src.tools.weight_tools import calculate_dynamic_k, get_connectivity_factor
from src.tools.value_assessor import get_value_assessor
from src.system.retry import call_with_retry
from src.system.config import load_config
from src.system.freeze import FreezeManager


class RecallManager:
    def __init__(self):
        self.context_snapshot = None
        self.freeze_manager = FreezeManager()
        config = load_config()
        self.timeout_seconds = config.get("freeze_timeout_seconds", 15)
        self.recalled_fingerprints = []  # 用于跟踪召回的fingerprints

    def execute_recall(self, request: dict) -> dict:
        """执行召回，支持超时回滚"""
        # 保存上下文快照（当前没有上下文，先模拟）
        self.context_snapshot = self._get_current_context()

        # 进入冻结态
        self.freeze_manager.freeze()

        start_time = time.time()

        try:
            recall_mode = request.get("mode", "implicit")
            normalized_user_request = request.get("request", "")
            recall_target = request.get("target", "")
            candidate_keys = request.get("keys", [])
            time_scope = request.get("time_scope")
            topk = request.get("topk", 2)

            # 调用路由Agent（模拟）
            if recall_mode == "explicit" and time_scope:
                # 时间回查模式
                routing_result = call_with_retry(
                    request_memory_recall,
                    recall_mode,
                    normalized_user_request,
                    recall_target,
                    candidate_keys,
                    time_scope,
                    topk,
                )
            else:
                # 语义召回模式
                if not candidate_keys:
                    from src.tools.key_tools import get_key_overview

                    overview = get_key_overview()
                    if overview["success"]:
                        candidate_keys = [k["key"] for k in overview["keys"]]

                routing_result = call_with_retry(
                    dispatch_recall_to_keys,
                    candidate_keys,
                    normalized_user_request,
                    recall_target,
                    topk,
                )

            if not routing_result.get("success", False):
                raise Exception("Routing failed")

            # 检查超时
            if time.time() - start_time > self.timeout_seconds:
                raise Exception("Recall timed out")

            # 处理结果
            if recall_mode == "explicit" and time_scope:
                # 时间回查结果
                time_query_result = routing_result.get("time_query_result", {})
                if time_query_result.get("success", False):
                    items = time_query_result.get("items", [])
                    recall_blocks = []
                    for i, item in enumerate(items, 1):
                        recall_blocks.append(
                            {
                                "index": i,
                                "key": "sub",
                                "time": item.get("created_at", ""),
                                "memory": item.get("raw_message", ""),
                            }
                        )
                else:
                    recall_blocks = []
            else:
                # 语义召回结果
                dispatch_items = routing_result.get("items", [])
                recall_blocks = self._process_dispatch_items(dispatch_items, topk)

            # 装配context_block
            context_block = self._format_recall_blocks(recall_blocks)

            # 成功：解冻
            self.freeze_manager.unfreeze()

            return {
                "success": True,
                "recall_blocks": recall_blocks,
                "context_block": context_block,
            }

        except Exception as e:
            # 失败/超时：回滚
            self._rollback()
            return {"success": False, "error": str(e), "can_retry": True}
        finally:
            # 更新recall_count
            if self.recalled_fingerprints:
                assessor = get_value_assessor()
                for fp in self.recalled_fingerprints:
                    if fp:
                        assessor.increment_recall_count(fp)

    def _get_current_context(self) -> dict:
        """获取当前上下文快照（模拟）"""
        return {"timestamp": time.time()}

    def _process_dispatch_items(self, items: list, topk: int) -> list:
        """处理dispatch结果，解析fingerprint为memory原文，使用动态topk"""
        recall_blocks = []
        index = 1
        self.recalled_fingerprints = []  # 清空并重新收集

        for item in items:
            key = item.get("key", "")
            main_fp_list = item.get(
                "main_fingerprints", []
            )  # [{fingerprint, weight, effective_strength}, ...]
            associated_fps_map = item.get(
                "associated_fingerprints", {}
            )  # {fp: [{fingerprint, weight, effective_strength}, ...]}

            # 收集所有fingerprint
            all_fps = set()
            for fp_data in main_fp_list:
                fp = fp_data["fingerprint"]
                all_fps.add(fp)
                self.recalled_fingerprints.append(fp)
                for associated in associated_fps_map.get(fp, []):
                    all_fps.add(associated["fingerprint"])
                    self.recalled_fingerprints.append(associated["fingerprint"])

            if not all_fps:
                continue

            # 批量获取memory
            fps_list = list(all_fps)
            result = get_memory_by_fp_list(fps_list)

            if not result.get("success", False):
                continue

            items_data = result.get("items", [])
            fp_to_memory = {}
            for item_data in items_data:
                if item_data.get("found", False):
                    fp_to_memory[item_data["fingerprint"]] = item_data

            # 按main_fingerprints顺序构建recall_blocks
            for fp_data in main_fp_list:
                fp = fp_data["fingerprint"]
                memory_weight = fp_data.get("weight", 0.5)
                edge_strength = fp_data.get("effective_strength", 0.5)

                if fp in fp_to_memory:
                    memory_data = fp_to_memory[fp]
                    recall_blocks.append(
                        {
                            "index": index,
                            "key": memory_data.get("key", key),
                            "time": memory_data.get("created_at", ""),
                            "memory": memory_data.get("memory", ""),
                        }
                    )
                    index += 1

                    # 计算动态关联数
                    c_conn = get_connectivity_factor(fp)
                    dynamic_k = calculate_dynamic_k(
                        memory_weight, edge_strength, c_conn
                    )

                    # 添加关联memory（使用动态k）
                    associated_list = associated_fps_map.get(fp, [])
                    for i, associated_data in enumerate(associated_list):
                        if i >= dynamic_k:
                            break
                        associated_fp = associated_data["fingerprint"]
                        if associated_fp in fp_to_memory:
                            memory_data = fp_to_memory[associated_fp]
                            recall_blocks.append(
                                {
                                    "index": index,
                                    "key": memory_data.get("key", key),
                                    "time": memory_data.get("created_at", ""),
                                    "memory": memory_data.get("memory", ""),
                                }
                            )
                            index += 1

        return recall_blocks

    def _format_recall_blocks(self, recall_blocks: list) -> str:
        """格式化recall_blocks为context_block"""
        lines = []
        for block in recall_blocks:
            lines.append(f"[{block['index']}]")
            lines.append(f"key: {block['key']}")
            lines.append(f"time: {block['time']}")
            lines.append(f"memory: {block['memory']}")
            lines.append("")
        return "\n".join(lines).strip()

    def _rollback(self):
        """回滚到召回前状态"""
        # 恢复上下文快照
        self._restore_context(self.context_snapshot)
        # 解冻
        self.freeze_manager.unfreeze()
        # 清空排队消息
        self.freeze_manager.clear_queue()

    def _restore_context(self, snapshot: dict):
        """
        恢复上下文快照

        注意：召回操作是只读操作（从数据库读取记忆），不修改任何数据。
        因此这里不需要真正的数据回滚，只需要恢复 freeze 状态即可。
        freeze/unfreeze 已在 _rollback 中处理。
        """
        pass

    def get_status(self) -> dict:
        """获取RecallManager状态"""
        return {
            "frozen": self.freeze_manager.is_frozen(),
            "freeze_status": self.freeze_manager.get_status(),
            "timeout_seconds": self.timeout_seconds,
        }

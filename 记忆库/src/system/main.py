"""统一入口 - 串联所有链路"""

import json
import time
from src.system.logger import get_module_logger
from src.system.storage_flow import process_user_message
from src.system.debug import debug_tool_call, DEBUG_MODE

logger = get_module_logger("main")
from src.tools.session_tools import append_to_session
from src.agents.dialogue import DialogueAgent
from src.agents.key_agent import KeyAgent
from src.system.context import assemble_context
from src.system.retry import call_with_retry
from src.tools.key_tools import list_all_keys
from src.tools.kb_tools import execute_kb_tool
from src.tools.key_tools import get_key_overview
from src.tools.memory_tools import list_memory_by_key, get_memories_by_key_sorted
from src.tools.query_tools import get_memory_by_fingerprint as get_memory_by_fp_list
from src.tools.weight_tools import calculate_dynamic_k, get_connectivity_factor
from src.tools.visibility_tools import update_visibility
from src.system.config import load_config
from src.tools.edge_calibrator import get_calibrator
from src.tools.topk_calculator import get_calculator
from src.tools.preference_tracker import get_preference_tracker

_system_prompt = """你是记忆助手，能够记住用户告诉你的事情，并在需要时回忆相关记忆。

## 你的能力
- 记住用户告诉你的事实、偏好、计划等
- 在对话中回忆相关的记忆
- 基于记忆提供个性化的回复

## 回复规则
- 如果有召回的记忆，结合记忆内容回复
- 如果没有记忆，自然地继续对话
- 保持友好、有帮助的语气
"""


def handle_user_message(
    message: str, turn_index: int, conversation_history: list = None, event_bus=None
) -> dict:
    """
    处理用户消息的完整链路
    1. 记录消息到会话文件（不存储到记忆库）
    2. 对话Agent循环（支持多轮tool-use）
    """
    logger.info(f"收到用户消息: {message[:50]}...")

    if conversation_history is None:
        conversation_history = []

    try:
        # 记录消息到会话文件（不存储到记忆库）
        append_to_session(message, turn_index)

        # 对话Agent循环（支持多轮tool-use）
        dialogue = DialogueAgent(list_all_keys())

        # 将 dialogue_messages 格式转换为 LLM 期望的格式，并添加当前用户消息
        if conversation_history:
            llm_history = []
            for entry in conversation_history:
                if entry.get("user_message"):
                    llm_history.append({"role": "user", "content": entry["user_message"]})
                if entry.get("assistant_message"):
                    llm_history.append({"role": "assistant", "content": entry["assistant_message"]})
            conversation_history = llm_history
        conversation_history.append({"role": "user", "content": message})

        max_iterations = 8
        tool_execution_start = None
        recalled_keys = set()

        for i in range(max_iterations):
            logger.info(f"[DialogueAgent] 内部第 {i + 1}/{max_iterations} 轮")
            iter_start = time.time()

            dialogue_result = call_with_retry(
                dialogue.receive_message,
                message if i == 0 else None,
                conversation_history if i == 0 else None,
            )

            iter_elapsed = time.time() - iter_start
            action = dialogue_result.get("action", "unknown")
            logger.info(
                f"[DialogueAgent] 第 {i + 1} 轮结果: {action} (耗时 {iter_elapsed:.1f}s)"
            )
            if action == "unknown":
                logger.warning(f"[DialogueAgent] 异常结果: {dialogue_result}")

            if dialogue_result.get("action") == "reply":
                reply = dialogue_result["content"]
                conversation_history.append({"role": "assistant", "content": reply})

                # 获取待上报的命中
                pending_hits = dialogue.get_pending_hits()
                has_recalled = dialogue.has_recalled()

                # 提交待上报的命中
                _submit_pending_hits(dialogue)

                # 计算总耗时（从首次工具执行到回复）
                total_elapsed = time.time() - iter_start
                if tool_execution_start is not None:
                    total_elapsed = time.time() - tool_execution_start

                # 轮次结束
                dialogue.reset_round_state()
                logger.info(f"消息处理完成 (总耗时 {total_elapsed:.1f}s)")

                return {
                    "success": True,
                    "action": "reply",
                    "content": reply,
                    "has_recalled": has_recalled,
                    "pending_hits": pending_hits,
                    "elapsed_seconds": round(total_elapsed, 2),
                }

            elif dialogue_result.get("action") == "tool_call":
                # 记录首次工具执行时间
                if tool_execution_start is None:
                    tool_execution_start = time.time()
                    logger.info(f"[Timing] 工具执行开始")

                tool_name = dialogue_result["tool_name"]
                tool_params = dialogue_result["params"]
                tool_call_id = dialogue_result.get("tool_call_id")

                logger.info(f"[DialogueAgent] 执行工具: {tool_name}")
                tool_start = time.time()
                # 执行工具
                if tool_name.startswith("kb_"):
                    tool_result = execute_kb_tool(tool_name, tool_params)
                elif tool_name == "get_key_summaries":
                    tool_result = _handle_get_key_summaries()
                elif tool_name in ("recall_from_key", "recall_from_keys"):
                    # 支持新参数 keys (array) 和旧参数 key (string)
                    keys_param = tool_params.get("keys")
                    key_param = tool_params.get("key", "")
                    if keys_param and isinstance(keys_param, list):
                        keys_to_use = keys_param
                    elif key_param:
                        keys_to_use = [key_param]
                    else:
                        keys_to_use = []

                    skip_keys = set()
                    for k in keys_to_use:
                        if k in recalled_keys:
                            skip_keys.add(k)
                        else:
                            recalled_keys.add(k)

                    if skip_keys and len(skip_keys) == len(keys_to_use):
                        logger.info(
                            f"[DialogueAgent] key(s) {skip_keys} 已召回过，跳过重复调用"
                        )
                        tool_result = {
                            "success": True,
                            "recall_blocks": [],
                            "content": f"key(s) {', '.join(skip_keys)} 已召回过相关记忆",
                        }
                    else:
                        tool_result = _handle_recall_from_key(
                            keys_to_use,
                            tool_params.get("query", ""),
                            conversation_history,
                            message,
                            dialogue,
                            tool_params.get("data")
                            or tool_params.get("date_range", ""),
                            event_bus=event_bus,
                        )
                elif tool_name == "save_to_key":
                    from src.system.storage_flow import _process_with_key_agent
                    from src.tools.visibility_tools import get_visible_memories

                    key = tool_params.get("key", "misc")
                    content = tool_params.get("content", "")
                    tag = tool_params.get(
                        "tag", content[:20] if len(content) > 20 else content
                    )

                    if not content:
                        tool_result = {"success": False, "error": "content is required"}
                    else:
                        existing_memories = get_visible_memories(key)
                        result = _process_with_key_agent(
                            key, content, tag, existing_memories, event_bus=event_bus
                        )

                        if result.get("success"):
                            tool_result = {
                                "success": True,
                                "action": result.get("action"),
                                "fingerprint": result.get("fingerprint"),
                                "key": key,
                            }
                            logger.info(
                                f"[save_to_key] 存储成功: key={key}, action={result.get('action')}"
                            )
                            if result.get("action") in ("added", "replaced"):
                                from src.system.storage_flow import (
                                    _process_cross_key_association,
                                )

                                try:
                                    _process_cross_key_association(
                                        result.get("fingerprint"),
                                        content,
                                        key,
                                        event_bus=event_bus,
                                    )
                                except Exception as e:
                                    logger.warning(
                                        f"[save_to_key] AssociationAgent failed: {e}"
                                    )
                        else:
                            tool_result = {
                                "success": False,
                                "error": result.get("error", "Unknown error"),
                            }
                elif tool_name == "report_hits":
                    fps = (
                        tool_params.get("fingerprints", [])
                        if isinstance(tool_params, dict)
                        else []
                    )
                    if fps:
                        calibrator = get_calibrator()
                        for fp in fps:
                            calibrator.record_hit(fp, fp)
                    tool_result = {"success": True, "content": "hits reported"}
                else:
                    tool_result = {
                        "success": False,
                        "error": f"Unknown tool: {tool_name}",
                    }

                tool_elapsed = time.time() - tool_start
                logger.info(
                    f"[DialogueAgent] 工具 {tool_name} 完成 (耗时 {tool_elapsed:.1f}s)"
                )

                # 先追加assistant消息（含tool_calls），再追加tool结果（标准 OpenAI 格式）
                dialogue.conversation_history.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tool_call_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": json.dumps(
                                        tool_params, ensure_ascii=False
                                    ),
                                },
                            }
                        ],
                    }
                )
                dialogue.conversation_history.append(
                    {
                        "role": "tool",
                        "content": json.dumps(tool_result, ensure_ascii=False),
                        "tool_call_id": tool_call_id,
                    }
                )

                # 如果recall_from_key有content，直接作为最终回复返回
                if tool_name in (
                    "recall_from_key",
                    "recall_from_keys",
                ) and tool_result.get("content"):
                    recall_content = tool_result["content"]
                    recall_blocks = tool_result.get("recall_blocks", [])
                    if recall_blocks:
                        dialogue.set_recall_blocks(recall_blocks)
                    dialogue.conversation_history.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": tool_call_id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(
                                            tool_params, ensure_ascii=False
                                        ),
                                    },
                                }
                            ],
                        }
                    )
                    dialogue.conversation_history.append(
                        {
                            "role": "tool",
                            "content": json.dumps(tool_result, ensure_ascii=False),
                            "tool_call_id": tool_call_id,
                        }
                    )
                    dialogue.conversation_history.append(
                        {"role": "assistant", "content": recall_content}
                    )
                    dialogue.reset_round_state()
                    _submit_pending_hits(dialogue)
                    logger.info("消息处理完成 (recall直接回复)")
                    return {
                        "success": True,
                        "action": "reply",
                        "content": recall_content,
                        "has_recalled": True,
                    }

                # 如果recall工具有新的recall_blocks，立即更新dialogue
                if tool_name in (
                    "recall_from_key",
                    "recall_from_keys",
                ) and tool_result.get("recall_blocks"):
                    dialogue.set_recall_blocks(tool_result["recall_blocks"])

                # 继续循环
                break

        dialogue.reset_round_state()
        _submit_pending_hits(dialogue)
        logger.info("消息处理完成")
        return {"success": True, "action": "reply", "content": "处理超时，请重试"}

    except Exception as e:
        logger.error(f"消息处理失败: {e}")
        return {"success": False, "error": str(e)}


def _handle_get_key_summaries() -> dict:
    """处理get_key_summaries工具"""
    overview = get_key_overview()
    if overview["success"]:
        summaries = {}
        for k in overview["keys"]:
            summaries[k["key"]] = {
                "summary": k.get("summary", ""),
                "memory_count": k.get("memory_count", 0),
            }
        return {"success": True, "key_summaries": summaries}
    return {"success": False, "error": overview.get("error")}


def _submit_pending_hits(dialogue: DialogueAgent):
    """提交待上报的命中指纹到后端（批量DB操作）"""
    hits = dialogue.get_pending_hits()
    if not hits:
        return

    calibrator = get_calibrator()
    processed_edges = set()

    # 增加记忆召回次数（批量）
    from src.tools.value_assessor import get_value_assessor

    assessor = get_value_assessor()
    for fp in hits:
        assessor.increment_recall_count(fp)

    # 批量查找所有相关边
    from src.tools.memory_tools import get_db

    conn = get_db()
    try:
        placeholders = ",".join("?" for _ in hits)
        edges = conn.execute(
            f"SELECT from_fingerprint, to_fingerprint FROM edges WHERE from_fingerprint IN ({placeholders}) OR to_fingerprint IN ({placeholders})",
            hits + hits,
        ).fetchall()
    finally:
        conn.close()

    for edge in edges:
        edge_key = (edge["from_fingerprint"], edge["to_fingerprint"])
        if edge_key not in processed_edges:
            processed_edges.add(edge_key)
            calibrator.record_hit(edge["from_fingerprint"], edge["to_fingerprint"])

    # 批量更新可见度
    for fp in hits:
        update_visibility(fp, "direct_hit")


def _analyze_hits_with_model(
    dialogue: DialogueAgent,
    user_message: str,
    reply: str,
    conversation_history: list,
    event_bus=None,
) -> list[str]:
    """后台调用单独的模型分析回复引用了哪些记忆，返回命中的fingerprints列表"""
    recall_blocks = dialogue.get_recall_blocks()
    if not recall_blocks or not reply:
        return []

    if event_bus:
        event_bus.emit_thinking("HitAnalyzer", "analyzing_response")

    blocks_text = "\n".join(
        f"[{b.get('fingerprint', '')}] {b.get('memory', '')}" for b in recall_blocks
    )

    # 格式化对话历史
    history_text = ""
    for entry in conversation_history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "tool":
            tc_id = entry.get("tool_call_id", "")
            history_text += f"[{role}#{tc_id}] {content}\n"
        else:
            history_text += f"[{role}] {content}\n"

    system_prompt = """你是记忆命中分析Agent。
给你【完整对话历史】和【本轮用户+回复】。
判断模型在各轮回复中引用了哪些记忆，通过add_pending_hit工具报告引用的指纹。"""

    user_prompt = f"""【完整对话历史】
{history_text}

【本轮用户消息】
{user_message}

【本轮模型回复】
{reply}

召回的记忆列表：
{blocks_text}

请分析模型在各轮回复中分别引用了哪些记忆。"""

    tools = [
        {
            "type": "function",
            "function": {
                "name": "add_pending_hit",
                "description": "添加命中的记忆指纹到待上报列表",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "fingerprint": {
                            "type": "string",
                            "description": "命中的记忆指纹",
                        },
                    },
                    "required": ["fingerprint"],
                },
            },
        }
    ]

    try:
        from src.system.llm_client import chat_completion

        response = chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            tools=tools,
            provider="deepseek",
        )

        fps = []
        choice = response.choices[0].message
        if choice.tool_calls:
            for tc in choice.tool_calls:
                if tc.function.name == "add_pending_hit":
                    args = json.loads(tc.function.arguments)
                    fp = args.get("fingerprint", "")
                    if fp:
                        fps.append(fp)
        return fps
    except Exception as e:
        logger.warning(f"模型分析hits失败: {e}")
        return []


RECALL_BATCH_SIZE = 8  # 每个KeyAgent负责的记忆数量


def _handle_recall_from_key(
    keys: list,
    query: str,
    conversation_history: list,
    message: str,
    dialogue: DialogueAgent,
    date_range: str = "",
    event_bus=None,
) -> dict:
    """
    处理recall_from_key/recall_from_keys工具（支持多key并发）
    流程：
    1. 先提交上次的命中统计
    2. 如果传了date_range，优先从sub获取该时间段的对话记录（不走key数据库）
    3. 否则走key数据库召回链路，对每个key并行执行KeyAgent判断
    """
    # 兼容旧版单key参数
    if isinstance(keys, str):
        keys = [keys]

    # 先提交上次的命中统计
    _submit_pending_hits(dialogue)

    # 如果传了date_range，优先从sub获取对话记录（纯数据库操作，无模型参与）
    if date_range:
        from src.tools.sub_tools import query_sub_by_time

        if "至" in date_range:
            start_date, end_date = date_range.split("至", 1)
        elif " " in date_range:
            start_date, end_date = date_range.split(" ", 1)
        else:
            start_date = end_date = date_range

        sub_result = query_sub_by_time(start_date.strip(), end_date.strip())
        if sub_result.get("success"):
            sub_records = sub_result.get("items", [])
            if sub_records:
                dialogue.record_recall_happened()
                if event_bus:
                    event_bus.emit_result(
                        "RecallAgent",
                        {
                            "success": True,
                            "count": len(sub_records),
                            "source": "conversation_history",
                        },
                    )
                return {
                    "success": True,
                    "content": f"找到{len(sub_records)}条{date_range}期间的对话记录",
                    "recall_blocks": [
                        {
                            "index": 1,
                            "type": "conversation_history",
                            "date_range": date_range,
                            "records": sub_records,
                        }
                    ],
                    "sub_records": sub_records,
                }

        dialogue.record_recall_happened()
        if event_bus:
            event_bus.emit_result(
                "RecallAgent",
                {"success": True, "count": 0, "source": "conversation_history"},
            )
        return {
            "success": True,
            "content": f"没有找到{date_range}期间的对话记录",
            "recall_blocks": [],
        }

    # 走key数据库召回链路（有KeyAgent模型参与）
    if event_bus:
        event_bus.emit_thinking("RecallAgent", f"searching_keys: {', '.join(keys)}")

    # 没有date_range，走key数据库召回链路
    tracker = get_preference_tracker()
    for key in keys:
        tracker.record_call(key)

    config = load_config()
    base_topk = config.get("topk_default", 2)

    # 计算 Top N = 100 / base_topk
    agent_top_n = max(10, min(100, round(100 / base_topk)))

    # 收集所有key的记忆，并行执行KeyAgent判断
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from src.system.llm_client import chat_completion

    all_relevant_fps = []

    def _key_agent_for_key(key: str):
        """对单个key执行完整的KeyAgent流程"""
        key_memories = get_memories_by_key_sorted(key, limit=agent_top_n)
        if not key_memories["success"]:
            return []

        memories = key_memories.get("memories", [])
        if not memories:
            return []

        existing_for_agent = [
            {"fingerprint": m["fingerprint"], "memory": m["memory"]} for m in memories
        ]

        # 分批：每批30条
        batches = [
            existing_for_agent[i : i + RECALL_BATCH_SIZE]
            for i in range(0, len(existing_for_agent), RECALL_BATCH_SIZE)
        ]

        key_relevant_fps = []

        def _key_agent_judge_batch(batch_idx, batch):
            agent_context = f"召回方向：{query}\n该key({key})下的记忆（第{batch_idx + 1}批，共{len(batches)}批）：\n{json.dumps(batch, ensure_ascii=False)}"

            response = chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": f"""你是"{key}"分类的记忆检索Agent。
根据用户的召回方向，从该分类下的记忆中判断哪些是相关的。

## 输入
- 召回方向：用户想找什么
- 记忆列表：包含指纹和原文

## 输出
调用get_relevant_memories工具，返回相关记忆的指纹列表。
如果没有相关记忆，返回空数组。
根据原文内容判断相关性。""",
                    },
                    {"role": "user", "content": agent_context},
                ],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "get_relevant_memories",
                            "description": "返回相关记忆的指纹列表",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "fingerprints": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "相关记忆的指纹列表",
                                    },
                                },
                                "required": ["fingerprints"],
                            },
                        },
                    }
                ],
                provider="deepseek",
            )
            if response.choices[0].message.tool_calls:
                args = json.loads(
                    response.choices[0].message.tool_calls[0].function.arguments
                )
                return args.get("fingerprints", [])
            return []

        # 串行处理每个key的batch（避免单个key内部并发过高）
        for i, batch in enumerate(batches):
            try:
                fps = _key_agent_judge_batch(i, batch)
                key_relevant_fps.extend(fps)
            except Exception as e:
                logger.error(f"KeyAgent {key} batch {i} failed: {e}")

        return list(set(key_relevant_fps))

    all_batches = []
    for key in keys:
        key_memories = get_memories_by_key_sorted(key, limit=agent_top_n)
        if not key_memories["success"]:
            continue
        memories = key_memories.get("memories", [])
        if not memories:
            continue
        existing_for_agent = [
            {"fingerprint": m["fingerprint"], "memory": m["memory"]} for m in memories
        ]
        batches = [
            existing_for_agent[i : i + RECALL_BATCH_SIZE]
            for i in range(0, len(existing_for_agent), RECALL_BATCH_SIZE)
        ]
        for batch_idx, batch in enumerate(batches):
            all_batches.append((key, batch_idx, batch))

    with ThreadPoolExecutor(
        max_workers=len(all_batches) if all_batches else 1
    ) as executor:
        futures = {
            executor.submit(
                _key_agent_judge_batch_global, key, batch_idx, batch, query, event_bus
            ): (key, batch_idx)
            for key, batch_idx, batch in all_batches
        }
        for future in as_completed(futures):
            key, batch_idx = futures[future]
            try:
                fps = future.result()
                all_relevant_fps.extend(fps)
            except Exception as e:
                logger.error(f"KeyAgent {key} batch {batch_idx} failed: {e}")

    # 去重
    relevant_fps = list(set(all_relevant_fps))

    if not relevant_fps:
        return {"success": True, "recall_blocks": [], "content": "没有找到相关记忆"}

    # 先用 base_topk 召回初始记忆用于多样性计算
    initial_blocks, expanded_fps = _expand_and_build_recall_blocks(
        relevant_fps, ", ".join(keys), base_topk
    )

    # 计算动态 topk
    calculator = get_calculator()
    context_length = len(_format_history(conversation_history))
    dynamic_topk = calculator.calculate(
        base_topk=base_topk,
        recall_blocks=initial_blocks,
        context_length=context_length,
        key=", ".join(keys),
    )

    # 如果动态 topk 不同，重新构建 recall_blocks
    if dynamic_topk != base_topk:
        recall_blocks, expanded_fps = _expand_and_build_recall_blocks(
            relevant_fps, key, dynamic_topk
        )
    else:
        recall_blocks = initial_blocks

    # 更新关联召回记忆的可见度
    for fp in expanded_fps:
        update_visibility(fp, "associated_recall")

    # 记录本次召回的指纹（用于去重）
    all_recall_fps = [
        block["fingerprint"] for block in recall_blocks if "fingerprint" in block
    ]
    dialogue.set_current_recall_fps(all_recall_fps)
    dialogue.record_recall_happened()

    # 记录边的召回次数
    calibrator = get_calibrator()
    processed_recall_edges = set()
    for block in recall_blocks:
        fp = block.get("fingerprint")
        if fp:
            from src.tools.memory_tools import get_db

            conn = get_db()
            try:
                edges = conn.execute(
                    "SELECT from_fingerprint, to_fingerprint FROM edges WHERE from_fingerprint = ? OR to_fingerprint = ?",
                    (fp, fp),
                ).fetchall()
            finally:
                conn.close()
            for edge in edges:
                edge_key = (edge["from_fingerprint"], edge["to_fingerprint"])
                if edge_key not in processed_recall_edges:
                    processed_recall_edges.add(edge_key)
                    calibrator.record_recall(
                        edge["from_fingerprint"], edge["to_fingerprint"]
                    )

    # 持久化召回记忆到DialogueAgent，直到下次召回被替换
    if recall_blocks:
        dialogue.set_recall_blocks(recall_blocks)

    if event_bus:
        event_bus.emit_result(
            "RecallAgent",
            {
                "success": True,
                "count": len(recall_blocks),
                "source": "key_database",
            },
        )

    return {
        "success": True,
        "recall_blocks": recall_blocks,
    }


def _expand_and_build_recall_blocks(direct_fps: list, key: str, topk: int) -> tuple:
    """通过edges图扩展召回，并构建recall_blocks，返回 (recall_blocks, expanded_fps)"""
    from src.tools.memory_tools import get_db
    from src.tools.query_tools import get_memory_by_fingerprint as get_fp_list
    from src.tools.cluster_engine import get_cluster_engine

    conn = get_db()
    try:
        all_fps = set(direct_fps)
        expanded_fps = {}

        for fp in direct_fps:
            edge_rows = conn.execute(
                """SELECT e.from_fingerprint, e.to_fingerprint, e.effective_strength
                   FROM edges e
                   WHERE (e.from_fingerprint = ? OR e.to_fingerprint = ?)
                   ORDER BY e.effective_strength DESC""",
                (fp, fp),
            ).fetchall()

            for edge in edge_rows:
                other_fp = (
                    edge["to_fingerprint"]
                    if edge["from_fingerprint"] == fp
                    else edge["from_fingerprint"]
                )
                if other_fp not in all_fps:
                    all_fps.add(other_fp)
                    expanded_fps[other_fp] = edge["effective_strength"]
    finally:
        conn.close()

    if not all_fps:
        return [], []

    result = get_fp_list(list(all_fps))
    if not result["success"]:
        return [], []

    fp_to_memory = {}
    for item in result["items"]:
        if item.get("found"):
            fp_to_memory[item["fingerprint"]] = item

    recall_blocks = []
    index = 1

    for fp in direct_fps:
        if fp in fp_to_memory:
            m = fp_to_memory[fp]
            recall_blocks.append(
                {
                    "index": index,
                    "key": m.get("key", key),
                    "tag": m.get("tag", ""),
                    "created_at": m.get("created_at", ""),
                    "memory": m.get("memory", ""),
                    "fingerprint": fp,
                    "recall_count": m.get("recall_count", 0),
                }
            )
            index += 1

    # 按聚类优先级排序扩展的记忆
    cluster_engine = get_cluster_engine()
    same_cluster = []
    diff_cluster = []

    for fp, strength in expanded_fps.items():
        is_same = False
        for direct_fp in direct_fps:
            if cluster_engine.are_same_cluster(fp, direct_fp):
                is_same = True
                break

        if is_same:
            same_cluster.append((fp, strength + 0.1))
        else:
            diff_cluster.append((fp, strength))

    all_expanded = same_cluster + diff_cluster
    all_expanded.sort(key=lambda x: x[1], reverse=True)

    for fp, strength in all_expanded[:topk]:
        if fp in fp_to_memory:
            m = fp_to_memory[fp]
            recall_blocks.append(
                {
                    "index": index,
                    "key": m.get("key", key),
                    "tag": m.get("tag", ""),
                    "created_at": m.get("created_at", ""),
                    "memory": m.get("memory", ""),
                    "fingerprint": fp,
                    "recall_count": m.get("recall_count", 0),
                }
            )
            index += 1

    return recall_blocks, list(expanded_fps.keys())


def _format_history(conversation_history: list) -> str:
    """格式化对话历史"""
    if not conversation_history:
        return ""

    limited = conversation_history[-20:]

    lines = []
    for msg in limited:
        role = msg.get("role", "")
        content = msg.get("content") or ""
        if role == "tool":
            continue
        if not content:
            continue
        role_text = "用户" if role == "user" else "助手"
        lines.append(f"{role_text}：{content}")

    result = "\n".join(lines)
    if len(result) > 4000:
        result = result[:4000]

    return result


def handle_user_message_streaming(
    message: str, turn_index: int, conversation_history: list = None, event_bus=None, persona: str = None
):
    """流式处理用户消息

    Yields:
        {"type": "reasoning", "content": str} - 思考过程（实时）
        {"type": "content", "delta": str} - 回复片段（实时）
        {"type": "done", "content": str, "has_recalled": bool} - 完成
        {"type": "error", "message": str} - 错误
    """
    import traceback

    logger.info(f"[Streaming] 收到用户消息: {message[:50]}...")

    if conversation_history is None:
        conversation_history = []

    try:
        append_to_session(message, turn_index)
        
        # 将用户消息持久化到历史档案库(sub表)
        from src.tools.sub_tools import insert_sub
        insert_sub(message, turn_index)

        dialogue = DialogueAgent(list_all_keys(), event_bus=event_bus, persona=persona)

        recalled_keys = set()
        max_iterations = 8

        for iteration in range(max_iterations):
            logger.info(
                f"[Streaming] DialogueAgent 第 {iteration + 1}/{max_iterations} 轮"
            )

            msg_to_send = message if iteration == 0 else None
            hist_to_send = conversation_history if (iteration == 0 and conversation_history) else None

            for event in dialogue.receive_message_streaming(msg_to_send, hist_to_send):
                event_type = event.get("type")

                if event_type == "reasoning":
                    # 实时输出思考过程
                    yield {
                        "type": "reasoning",
                        "content": event.get("delta", event.get("content", "")),
                    }

                elif event_type == "content":
                    # 实时输出回复片段
                    yield {"type": "content", "delta": event["delta"]}

                elif event_type == "reply":
                    # 最终回复
                    reply = event["content"]
                    conversation_history.append({"role": "assistant", "content": reply})
                    
                    # 将助手的回复也存入历史档案库(sub表)
                    from src.tools.sub_tools import insert_sub
                    insert_sub(f"助手：{reply}", turn_index)
                    append_to_session(f"助手：{reply}", turn_index)

                    # 后台异步调用单独的分析agent分析回复引用了哪些记忆（不计入streaming时间）
                    import threading

                    t = threading.Thread(
                        target=_analyze_hits_with_model,
                        args=(
                            dialogue,
                            message,
                            reply,
                            conversation_history,
                            event_bus,
                        ),
                    )
                    t.daemon = True
                    t.start()

                    _submit_pending_hits(dialogue)
                    has_recalled = dialogue.has_recalled()
                    recall_blocks = dialogue.get_recall_blocks()
                    dialogue.reset_round_state()
                    yield {
                        "type": "done",
                        "content": reply,
                        "has_recalled": has_recalled,
                        "recall_blocks": recall_blocks,
                    }
                    return

                elif event_type == "tool_call":
                    tool_name = event["tool_name"]
                    tool_params = event["params"]
                    tool_call_id = event["tool_call_id"]
                    reasoning = event.get("reasoning", "")

                    logger.info(f"[Streaming] 执行工具: {tool_name}")

                    if event_bus:
                        event_bus.emit_tool_call(
                            "DialogueAgent", tool_name, tool_params
                        )

                    if tool_name.startswith("kb_"):
                        if event_bus:
                            event_bus.emit_thinking("KBTool", f"executing {tool_name}")
                        tool_result = execute_kb_tool(tool_name, tool_params)
                        if event_bus:
                            event_bus.emit_result(
                                "KBTool",
                                {
                                    "tool": tool_name,
                                    "success": tool_result.get("success", False),
                                },
                            )
                    elif tool_name == "get_key_summaries":
                        tool_result = _handle_get_key_summaries()
                        if event_bus:
                            event_bus.emit_result(
                                "RecallAgent",
                                {
                                    "success": tool_result.get("success", False),
                                    "key_summaries_count": len(tool_result.get("key_summaries", {})),
                                },
                            )
                    elif tool_name in ("recall_from_key", "recall_from_keys"):
                        keys_param = tool_params.get("keys")
                        key_param = tool_params.get("key", "")
                        if keys_param and isinstance(keys_param, list):
                            keys_to_use = keys_param
                        elif key_param:
                            keys_to_use = [key_param]
                        else:
                            keys_to_use = []

                        skip_keys = set()
                        for k in keys_to_use:
                            if k in recalled_keys:
                                skip_keys.add(k)
                            else:
                                recalled_keys.add(k)

                        if skip_keys and len(skip_keys) == len(keys_to_use):
                            tool_result = {
                                "success": True,
                                "recall_blocks": [],
                                "content": f"key(s) {', '.join(skip_keys)} 已召回过相关记忆",
                            }
                        else:
                            tool_result = _handle_recall_from_key(
                                keys_to_use,
                                tool_params.get("query", ""),
                                conversation_history,
                                message,
                                dialogue,
                                tool_params.get("data")
                                or tool_params.get("date_range", ""),
                                event_bus=event_bus,
                            )
                    elif tool_name == "save_to_key":
                        from src.system.storage_flow import _process_with_key_agent
                        from src.tools.visibility_tools import get_visible_memories

                        key = tool_params.get("key", "misc")
                        content = tool_params.get("content", "")
                        tag = tool_params.get(
                            "tag", content[:20] if len(content) > 20 else content
                        )

                        if not content:
                            tool_result = {
                                "success": False,
                                "error": "content is required",
                            }
                        else:
                            existing_memories = get_visible_memories(key)
                            result = _process_with_key_agent(
                                key,
                                content,
                                tag,
                                existing_memories,
                                event_bus=event_bus,
                            )

                            if result.get("success"):
                                tool_result = {
                                    "success": True,
                                    "action": result.get("action"),
                                    "fingerprint": result.get("fingerprint"),
                                    "key": key,
                                }
                                logger.info(
                                    f"[save_to_key] 存储成功: key={key}, action={result.get('action')}"
                                )
                                if result.get("action") in ("added", "replaced"):
                                    from src.system.storage_flow import (
                                        _process_cross_key_association,
                                    )

                                    try:
                                        _process_cross_key_association(
                                            result.get("fingerprint"),
                                            content,
                                            key,
                                            event_bus=event_bus,
                                        )
                                    except Exception as e:
                                        logger.warning(
                                            f"[save_to_key] AssociationAgent failed: {e}"
                                        )

                                if event_bus:
                                    event_bus.emit_result(
                                        "StorageAgent",
                                        {
                                            "action": result.get("action"),
                                            "key": key,
                                            "fingerprint": result.get(
                                                "fingerprint", ""
                                            )[:12],
                                        },
                                    )
                            else:
                                tool_result = {
                                    "success": False,
                                    "error": result.get("error", "Unknown error"),
                                }
                    elif tool_name == "report_hits":
                        fps = (
                            tool_params.get("fingerprints", [])
                            if isinstance(tool_params, dict)
                            else []
                        )
                        if fps:
                            calibrator = get_calibrator()
                            for fp in fps:
                                calibrator.record_hit(fp, fp)
                        tool_result = {"success": True, "content": "hits reported"}
                    else:
                        tool_result = {
                            "success": False,
                            "error": f"Unknown tool: {tool_name}",
                        }

                    if event_bus:
                        event_bus.emit_result(
                            "DialogueAgent",
                            {
                                "tool": tool_name,
                                "success": tool_result.get("success", False),
                            },
                        )

                    # 追加工具调用记录到对话历史
                    dialogue.conversation_history.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": tool_call_id,
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": json.dumps(
                                            tool_params, ensure_ascii=False
                                        ),
                                    },
                                }
                            ],
                        }
                    )

                    # 对于 recall_from_key/recall_from_keys，把 JSON 替换成格式化文本
                    if tool_name in ("recall_from_key", "recall_from_keys"):
                        from src.system.context import format_recall_blocks

                        recall_blocks = tool_result.get("recall_blocks", [])
                        if recall_blocks:
                            dialogue.set_recall_blocks(recall_blocks)
                            dialogue.record_recall_happened()
                            tool_content = format_recall_blocks(recall_blocks)
                        else:
                            tool_content = tool_result.get("content", "")
                    else:
                        tool_content = json.dumps(tool_result, ensure_ascii=False)

                    dialogue.conversation_history.append(
                        {
                            "role": "tool",
                            "content": tool_content,
                            "tool_call_id": tool_call_id,
                        }
                    )

                    # 将工具返回事件 yield 到 SSE，让前端能展示
                    yield {
                        "type": "tool_return",
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "result": tool_content,
                    }

                    # 继续循环，处理工具执行结果
                    break

    except Exception as e:
        logger.error(f"[Streaming] 消息处理失败: {e}\n{traceback.format_exc()}")
        yield {"type": "error", "message": str(e)}


def _key_agent_judge_batch_global(
    key: str, batch_idx: int, batch: list, query: str, ev_bus
):
    """全局函数：对单个key的单个batch执行KeyAgent判断（用于并发池）"""
    agent_context = f"召回方向：{query}\n该key({key})下的记忆（第{batch_idx + 1}批）：\n{json.dumps(batch, ensure_ascii=False)}"

    if ev_bus:
        ev_bus.emit_thinking("KeyAgent", f"judging key={key} batch={batch_idx + 1}")

    response = chat_completion(
        messages=[
            {
                "role": "system",
                "content": f"""你是"{key}"分类的记忆检索Agent。
根据用户的召回方向，从该分类下的记忆中判断哪些是相关的。

## 输入
- 召回方向：用户想找什么
- 记忆列表：包含指纹和原文

## 输出
调用get_relevant_memories工具，返回相关记忆的指纹列表。
如果没有相关记忆，返回空数组。
根据原文内容判断相关性。""",
            },
            {"role": "user", "content": agent_context},
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "get_relevant_memories",
                    "description": "返回相关记忆的指纹列表",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "fingerprints": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "相关记忆的指纹列表",
                            },
                        },
                        "required": ["fingerprints"],
                    },
                },
            }
        ],
        provider="deepseek",
    )
    fps = []
    if response.choices[0].message.tool_calls:
        try:
            args = json.loads(
                response.choices[0].message.tool_calls[0].function.arguments
            )
            fps = args.get("fingerprints", [])
        except Exception as e:
            logger.error(f"KeyAgent {key} batch {batch_idx} parse error: {e}")

    if ev_bus and fps:
        ev_bus.emit_result(
            "KeyAgent", {"key": key, "batch": batch_idx + 1, "success": len(fps)}
        )

    return fps

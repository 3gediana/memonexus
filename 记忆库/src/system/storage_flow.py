import json
import time
from src.system.logger import get_module_logger
from src.tools.sub_tools import insert_sub

logger = get_module_logger("storage")
from src.tools.routing_tools import assign_memory_to_keys
from src.tools.memory_tools import (
    add_memory_to_key,
    delete_memory_from_key,
    replace_memory_in_key,
)
from src.tools.visibility_tools import get_visible_memories, HIDDEN_THRESHOLD
from src.tools.edge_tools import create_edges
from src.tools.query_tools import get_cross_key_context
from src.system.retry import call_with_retry
from src.system.config import load_config
from src.agents.routing import RoutingAgent
from src.agents.key_agent import KeyAgent
from src.agents.association import AssociationAgent
from src.tools.association_scorer import get_scorer
from src.tools.key_tools import BUILT_IN_KEYS
from src.tools.cluster_service import assign_memory_to_cluster, complete_cluster_merge

BATCH_SIZE = 8  # 每批注入的记忆数量
PRUNE_CHECK_INTERVAL = 10  # 每N次存储检查一次淘汰
_prune_counter = 0


def _generate_tag_with_llm(memory: str, key: str) -> str:
    """系统自动生成tag，涵盖所有关键信息"""
    from src.system.llm_client import chat_completion

    try:
        response = chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": f"""你是tag生成助手。将记忆缩写为tag，要求：
1. 涵盖时间、地点、人物、事件、对象等所有关键信息
2. 长度不超过原文
3. 直接输出tag，不要任何解释

key：{key}""",
                },
                {"role": "user", "content": memory},
            ],
            provider="deepseek",
        )
        tag = response.choices[0].message.content.strip()
        # 确保不超过原文长度
        if len(tag) > len(memory):
            tag = tag[: len(memory)]
        return tag
    except Exception:
        # 降级：截取前20字
        return memory[:20]


def _rollback_memories(fingerprints: list[str]):
    """回滚：删除已添加的memory"""
    for fp in fingerprints:
        _delete_memory_by_fp(fp)


def _delete_memory_by_fp(fingerprint: str) -> dict:
    """通过fingerprint删除memory"""
    from src.tools.memory_tools import get_db

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT key FROM memory WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
        if row:
            key = row["key"]
            return delete_memory_from_key(key, fingerprint)
        return {"success": False, "error": "FP_NOT_FOUND"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def _process_with_key_agent(
    key: str, memory: str, tag: str, existing_memories: list
) -> dict:
    """
    使用KeyAgent处理单条候选记忆（悬空记忆阶段）

    阶段1：决策
    - 输入：tag-指纹列表（无原文）
    - 工具：get_memory_by_fingerprint（可查原文）
    - 输出：add/replace/reject/duplicate

    阶段2：建边（独立，上下文隔离）
    - 输入：8条原文窗口
    - 工具：只有build_edges
    """
    # 阶段1：决策（给tag-指纹列表，模型可自行查询原文）
    agent = KeyAgent(key)
    result = agent.process_candidate(memory, tag, existing_memories)

    action = result.get("action")
    args = result.get("args", {})

    # 模型返回 none 时，视为 reject
    if action == "none":
        logger.warning(f"KeyAgent 3次尝试均未调用工具，reject (key={key})")
        return {
            "success": True,
            "action": "rejected",
            "reason": "KeyAgent 无法判断",
        }

    if action == "add_memory_to_key":
        resolved_tag = args.get("tag", tag)
        importance_score = args.get("importance_score", 0.5)

        # 执行存储，记忆落位，获得指纹
        add_result = add_memory_to_key(
            args.get("key", key),
            args.get("memory", memory),
            resolved_tag,
            args.get("summary_item", memory[:50]),
            base_score=importance_score,
        )
        if add_result["success"]:
            # 校验 tag 不为空
            if not resolved_tag:
                logger.warning(f"存储后 tag 为空，reject (key={key})")
                _delete_memory_by_fp(add_result["added"]["fingerprint"])
                return {"success": False, "error": "EMPTY_TAG"}

            new_fp = add_result["added"]["fingerprint"]

            # 阶段1.5：记忆簇分配（语义相似度检测 + 自动打包）
            cluster_result = _assign_to_cluster(new_fp, key, memory, resolved_tag)

            # 阶段2：分批建边（独立上下文，传入原文）
            same_key_edges = _build_same_key_edges_batched(new_fp, key, memory)

            # 如果触发了合并，执行 LLM 合并
            merged_memory = None
            final_fp = new_fp
            if cluster_result.get("merged"):
                merge_result = _merge_cluster(
                    cluster_result["cluster_id"], cluster_result["merged_memories"]
                )
                if merge_result.get("success"):
                    merged_memory = merge_result.get("merged_memory")
                    final_fp = merge_result.get("fingerprint")
                    # 合并后的新记忆重新建边
                    same_key_edges = _build_same_key_edges_batched(
                        final_fp, key, merged_memory
                    )

            return {
                "success": True,
                "action": "added",
                "fingerprint": final_fp,
                "memory": merged_memory or memory,
                "key": key,
                "tag": resolved_tag,
                "same_key_edges": same_key_edges,
                "cluster_id": cluster_result.get("cluster_id"),
                "merged": cluster_result.get("merged", False),
                "merged_memory": merged_memory,
            }
        return {"success": False, "error": add_result.get("error")}

    elif action == "replace_memory_in_key":
        old_fp = args.get("old_fingerprint")

        # 先查询旧记忆的边，用于失败时回滚
        old_edges = _get_edges_for_fingerprint(old_fp)

        replace_result = replace_memory_in_key(
            args.get("key", key),
            old_fp,
            args.get("new_memory", memory),
            args.get("new_tag", tag),
            args.get("new_summary_item", memory[:50]),
        )
        if replace_result["success"]:
            new_fp = replace_result["added"]["fingerprint"]

            # 阶段2：分批建边（独立上下文，传入原文）
            same_key_edges = _build_same_key_edges_batched(new_fp, key, memory)

            # 如果边建立失败，尝试用旧边重建
            if not same_key_edges.get("success") and old_edges:
                _recreate_edges_for_new_fp(new_fp, old_fp, old_edges)

            return {
                "success": True,
                "action": "replaced",
                "fingerprint": new_fp,
                "memory": memory,
                "key": key,
                "tag": tag,
                "same_key_edges": same_key_edges,
            }
        return {"success": False, "error": replace_result.get("error")}

    elif action == "reject_candidate":
        return {
            "success": True,
            "action": "rejected",
            "reason": args.get("reason", "不属于本key"),
        }

    elif action == "mark_duplicate":
        return {
            "success": True,
            "action": "duplicate",
            "existing_fingerprint": args.get("existing_fingerprint"),
        }

    return {"success": False, "error": "UNKNOWN_ACTION"}


def _get_visible_memories_with_content(key: str) -> list:
    """获取可见记忆的完整内容（用于建边阶段）"""
    try:
        from src.tools.memory_tools import get_db

        conn = get_db()
        rows = conn.execute(
            "SELECT fingerprint, tag, memory, key FROM memory WHERE key = ? AND (visibility IS NULL OR visibility >= ?)",
            (key, HIDDEN_THRESHOLD),
        ).fetchall()
        conn.close()
        return [dict(row) for row in rows]
    except Exception:
        return []


def _get_memory_content_by_fp(fp: str) -> str:
    """根据指纹获取记忆内容"""
    try:
        from src.tools.memory_tools import get_db

        conn = get_db()
        row = conn.execute(
            "SELECT memory FROM memory WHERE fingerprint = ?", (fp,)
        ).fetchone()
        conn.close()
        return row["memory"] if row else ""
    except Exception:
        return ""


def _build_same_key_edges_batched(new_fp: str, key: str, new_memory: str) -> dict:
    """
    分批建立同key关联边

    系统维护滑动窗口，每批注入 BATCH_SIZE 条已有记忆（含原文）给 KeyAgent，
    处理完后清空上下文，滑动到下一批。已处理的记忆不再出现。
    建边阶段与存储决策阶段上下文隔离。
    """
    existing_memories = _get_visible_memories_with_content(key)
    if not existing_memories:
        return {"success": True, "edges_created": 0}

    agent = KeyAgent(key)
    total_edges_created = 0

    # 分批处理
    for i in range(0, len(existing_memories), BATCH_SIZE):
        batch = existing_memories[i : i + BATCH_SIZE]

        # 调用 KeyAgent 判断与当前批次的边
        result = agent._build_edges_for_batch(new_fp, new_memory, batch)
        if result.get("success"):
            edges = result.get("edges", [])
            if edges:
                edge_result = _create_same_key_edges(new_fp, edges)
                total_edges_created += edge_result.get("created_count", 0)

    return {"success": True, "edges_created": total_edges_created}


def _create_same_key_edges(from_fp: str, edges: list) -> dict:
    """建立同key关联边"""
    if not edges:
        return {"success": True}

    edge_list = []
    for edge in edges:
        edge_list.append(
            {
                "from_fingerprint": from_fp,
                "to_fingerprint": edge["target_fingerprint"],
                "strength": edge["strength"],
                "reason": edge["reason"],
            }
        )
    return create_edges(edge_list)


def _get_edges_for_fingerprint(fingerprint: str) -> list:
    """获取记忆的所有边"""
    from src.tools.memory_tools import get_db

    try:
        conn = get_db()
    except Exception:
        return []
    try:
        rows = conn.execute(
            "SELECT from_fingerprint, to_fingerprint, strength, reason FROM edges WHERE from_fingerprint = ? OR to_fingerprint = ?",
            (fingerprint, fingerprint),
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []
    finally:
        conn.close()


def _recreate_edges_for_new_fp(new_fp: str, old_fp: str, old_edges: list):
    """用旧边信息为新记忆重建边"""
    if not old_edges:
        return
    edge_list = []
    for edge in old_edges:
        if edge["from_fingerprint"] == old_fp:
            edge_list.append(
                {
                    "from_fingerprint": new_fp,
                    "to_fingerprint": edge["to_fingerprint"],
                    "strength": edge["strength"],
                    "reason": edge["reason"],
                }
            )
        elif edge["to_fingerprint"] == old_fp:
            edge_list.append(
                {
                    "from_fingerprint": edge["from_fingerprint"],
                    "to_fingerprint": new_fp,
                    "strength": edge["strength"],
                    "reason": edge["reason"],
                }
            )
    if edge_list:
        create_edges(edge_list)


def _process_cross_key_association(fingerprint: str, memory: str, key: str) -> dict:
    """
    处理跨key关联（AssociationAgent）

    系统自动准备：
    - 主记忆：fingerprint + tag + memory
    - 其他key下的所有记忆：fingerprint + tag（预筛，排除自己key下的）
    - 分批处理：每批最多 BATCH_SIZE 条候选
    """
    try:
        cross_context = get_cross_key_context(fingerprint)
        if not cross_context["success"]:
            return {"success": False, "error": cross_context.get("error")}

        candidates = cross_context.get("candidates", [])
        if not candidates:
            return {"success": True, "edges_created": 0}

        main_memory = cross_context["main_memory"]

        # 算法预打分
        scorer = get_scorer()
        scored_candidates = scorer.score_candidates(main_memory, candidates)

        # 只保留分数>0.05的候选（低阈值，避免漏掉隐式关联）
        filtered_candidates = [c for c in scored_candidates if c["algo_score"] > 0.05]

        if not filtered_candidates:
            return {"success": True, "edges_created": 0}

        # 分批处理跨key关联
        total_edges_created = 0
        agent = AssociationAgent()

        for i in range(0, len(filtered_candidates), BATCH_SIZE):
            batch = filtered_candidates[i : i + BATCH_SIZE]
            edges = agent.process(main_memory, batch)

            if edges:
                edge_list = []
                for edge in edges:
                    edge_list.append(
                        {
                            "from_fingerprint": fingerprint,
                            "to_fingerprint": edge["target_fingerprint"],
                            "strength": edge["strength"],
                            "reason": edge["reason"],
                        }
                    )
                result = create_edges(edge_list)
                total_edges_created += result.get("created_count", 0)

        return {"success": True, "edges_created": total_edges_created}
    except Exception as e:
        logger.error(f"Cross-key association failed for {fingerprint}: {e}")
        return {"success": False, "error": str(e)}


def _check_and_prune_if_needed():
    """检查记忆数量，超阈值时触发价值评估与淘汰"""
    global _prune_counter
    try:
        _prune_counter += 1
        if _prune_counter < PRUNE_CHECK_INTERVAL:
            return

        _prune_counter = 0

        from src.tools.value_assessor import get_value_assessor

        assessor = get_value_assessor()
        count = assessor.get_memory_count()

        config = load_config()
        threshold = config.get("memory_prune_threshold", 500)

        if count >= threshold:
            logger.info(f"记忆数量 {count} 超过阈值 {threshold}，触发价值评估与淘汰")
            assessor.update_all_values()
            prune_result = assessor.prune_low_value_memories()
            if prune_result.get("pruned", 0) > 0:
                logger.info(f"淘汰完成: 删除 {prune_result['pruned']} 条低价值记忆")
            else:
                logger.info(
                    f"无需淘汰: {prune_result.get('reason', '无符合条件的记忆')}"
                )
    except Exception as e:
        logger.warning(f"淘汰检查失败: {e}")


def process_user_message(message: str, turn_index: int) -> dict:
    """
    存储流程编排

    流程：
    1. RoutingAgent：分配key
    2. KeyAgent：处理悬空记忆（判断操作 + 同key关联）
    3. 系统：执行存储，记忆落位，分配指纹
    4. 系统：建立同key关联边
    5. 系统：触发AssociationAgent处理跨key关联
    """
    logger.info(f"开始存储流程: turn={turn_index}")
    config = load_config()

    # 检查点1：写入sub（不回滚）
    sub_result = insert_sub(message, turn_index)
    if not sub_result.get("success", False):
        logger.error("SUB写入失败")
        return {"success": False, "error": "SUB_WRITE_FAILED"}

    sub_id = sub_result["id"]

    # 检查点2：调用RoutingAgent分析
    routing_agent = RoutingAgent(BUILT_IN_KEYS)
    candidates = call_with_retry(routing_agent.analyze_message, message)

    if not candidates:
        return {"success": True, "sub_id": sub_id, "memories_added": [], "rejected": []}

    # 检查点3：分配key
    assign_result = call_with_retry(assign_memory_to_keys, candidates)
    if not assign_result.get("success", False):
        return {
            "success": False,
            "error": "ASSIGN_FAILED",
            "can_retry": True,
            "sub_id": sub_id,
        }

    accepted = assign_result.get("accepted", [])
    rejected = assign_result.get("rejected", [])

    # 检查点4：调用KeyAgent处理每条候选记忆（决策 + 同key建边）
    added_memories = []
    added_fps = []
    failed_items = []

    for item in accepted:
        key = item["target_key"]
        memory = item["memory"]

        # 系统判断字数：≤20字直接用原文作为tag，>20字让KeyAgent自己生成
        if len(memory) <= 20:
            pre_tag = memory
        else:
            pre_tag = ""

        # 获取该key下的已有记忆（仅可见记忆）
        existing_memories = get_visible_memories(key)

        # KeyAgent处理：模型失败重试3次，系统异常直接回滚
        max_retries = 3
        result = None
        for attempt in range(max_retries):
            try:
                result = _process_with_key_agent(
                    key, memory, pre_tag, existing_memories
                )
                if result.get("success", False):
                    break
                # 模型返回失败，重试
                if attempt < max_retries - 1:
                    logger.warning(f"KeyAgent第{attempt + 1}次失败，重试: key={key}")
            except Exception as e:
                # 系统异常：回滚所有已存储的记忆
                logger.error(f"KeyAgent系统异常，回滚: key={key}, error={e}")
                _rollback_memories(added_fps)
                return {
                    "success": False,
                    "error": f"SYSTEM_ERROR: {e}",
                    "can_retry": True,
                    "sub_id": sub_id,
                }

        if result and result.get("success", False):
            if result["action"] in ("added", "replaced"):
                new_fp = result.get("fingerprint")
                added_memories.append(
                    {
                        "key": key,
                        "fingerprint": new_fp,
                        "memory": memory,
                        "tag": result.get("tag", ""),
                    }
                )
                added_fps.append(new_fp)
        else:
            failed_items.append(
                {
                    "key": key,
                    "memory": memory,
                    "error": result.get("error") if result else "NO_RESULT",
                }
            )
            logger.warning(f"KeyAgent处理失败（{max_retries}次重试）: key={key}")

    if failed_items:
        logger.warning(
            f"存储部分成功: added={len(added_memories)}, failed={len(failed_items)}"
        )

    # 检查点5：KeyAgent完全静息后，统一触发跨key关联（AssociationAgent）
    for item in added_memories:
        assoc_result = _process_cross_key_association(
            item["fingerprint"], item["memory"], item["key"]
        )
        if not assoc_result.get("success"):
            logger.warning(
                f"Cross-key association failed for {item['fingerprint']}: {assoc_result.get('error')}"
            )

    # 检查点6：记忆数量超阈值时触发价值评估与淘汰
    _check_and_prune_if_needed()

    logger.info(f"存储完成: added={len(added_memories)}")
    return {
        "success": True,
        "sub_id": sub_id,
        "memories_added": added_memories,
        "rejected": rejected,
    }


def _assign_to_cluster(fingerprint: str, key: str, memory: str, tag: str) -> dict:
    """记忆落位后分配到簇"""
    try:
        return assign_memory_to_cluster(fingerprint, key, memory, tag)
    except Exception as e:
        logger.warning(f"簇分配失败: {e}")
        return {"success": False, "error": str(e), "merged": False}


def _merge_cluster(cluster_id: str, memories: list) -> dict:
    """LLM 合并簇内记忆（模型自行判断是否合并）"""
    try:
        from src.system.llm_client import chat_completion
        from src.system.fingerprint import generate_fingerprint, get_utc_now
        from src.tools.memory_tools import get_db

        # 构建合并 prompt
        memory_texts = "\n".join(
            [f"- [{m['created_at']}] {m['memory']}" for m in memories]
        )

        prompt = f"""你是记忆合并助手。以下记忆被语义相似度算法归为同一簇，但它们不一定都能合并。

## 原始记忆
{memory_texts}

## 你的任务
判断这些记忆是否可以合并为一条：
1. 如果可以合并 → 按格式输出合并后的记忆和 tag
2. 如果不应合并 → 输出 "KEEP_SEPARATE"

## 判断原则
**可合并的情况**：
- 描述同一事件的不同角度/补充信息（如"买了高数书"+"报了政治课"都是考研准备）
- 状态更新（新状态替代旧状态，如"开始准备考研"+"已经考完研了"→合并为一条完整时间线）
- 同一时间点的多条相关信息（如"每天学8小时"+"7点起床"+"晚上11点回"）

**不应合并的情况**：
- 每条记录的是同一主题的序列进度（如"复习第一章"+"复习第二章"+"复习第三章"→每条是独立进度，合并会丢失细节）
- 合并会丢失重要的序列信息或进度细节
- 记忆之间只是主题相关，但描述的是不同独立事件

## 输出格式（合并时）
第一行：MERGED_MEMORY: 合并后的记忆文本
第二行：MERGED_TAG: 新 tag（涵盖所有关键信息，包含时间）

## 输出格式（不合并时）
KEEP_SEPARATE
"""

        response = chat_completion(
            messages=[{"role": "user", "content": prompt}],
            provider="deepseek",
        )

        result_text = response.choices[0].message.content.strip()

        # 模型判断不合并
        if result_text == "KEEP_SEPARATE":
            return {"success": True, "merged": False, "reason": "模型判断不应合并"}

        # 解析合并结果
        merged_text = ""
        merged_tag = ""
        for line in result_text.split("\n"):
            if line.startswith("MERGED_MEMORY:"):
                merged_text = line[len("MERGED_MEMORY:") :].strip()
            elif line.startswith("MERGED_TAG:"):
                merged_tag = line[len("MERGED_TAG:") :].strip()

        if not merged_text:
            return {"success": False, "error": "LLM 输出格式错误"}

        merged_fp = generate_fingerprint(merged_text)
        if not merged_tag:
            merged_tag = merged_text[:20] if len(merged_text) <= 20 else ""

        # 完成合并（删除旧记忆，插入新记忆，重建边）
        result = _complete_merge_with_rebuild(
            cluster_id, merged_fp, merged_text, merged_tag
        )

        if result.get("success"):
            return {
                "success": True,
                "merged_memory": merged_text,
                "fingerprint": merged_fp,
            }
        return {"success": False, "error": result.get("error")}

    except Exception as e:
        logger.error(f"簇合并失败: {e}")
        return {"success": False, "error": str(e)}


def _complete_merge_with_rebuild(cluster_id, merged_fp, merged_text, merged_tag):
    """完成合并：使用 complete_cluster_merge 在单个事务中完成所有操作"""
    try:
        from src.tools.memory_tools import get_db
        from src.system.fingerprint import get_utc_now

        # 使用 complete_cluster_merge 在单个事务中完成：
        # 1. 获取旧边 2. 删除旧记忆 3. 插入新记忆 4. 重定向边 5. 更新簇
        merge_result = complete_cluster_merge(
            cluster_id, merged_fp, merged_text, merged_tag
        )
        if not merge_result.get("success"):
            return {"success": False, "error": merge_result.get("error")}

        actual_fp = merge_result["new_fingerprint"]

        # 合并后的新记忆重新建边（同key边）
        conn = get_db()
        try:
            key = conn.execute(
                "SELECT key FROM memory WHERE fingerprint = ?", (actual_fp,)
            ).fetchone()["key"]
        finally:
            conn.close()

        _build_same_key_edges_batched(actual_fp, key, merged_text)

        return {
            "success": True,
            "fingerprint": actual_fp,
            "new_cluster_id": merge_result.get("new_cluster_id"),
        }

    except Exception as e:
        return {"success": False, "error": str(e)}

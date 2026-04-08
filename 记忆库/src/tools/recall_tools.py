import uuid
from src.tools.query_tools import get_key_context
from src.tools.key_tools import get_key_overview
from src.tools.memory_tools import get_db
from src.tools.sub_tools import query_sub_by_time


def dispatch_recall_to_keys(
    candidate_keys: list[str],
    normalized_user_request: str,
    recall_target: str,
    topk: int = 2,
) -> dict:
    """
    基于 recall_target 直接用 edges 关联召回相关记忆。
    存储时 KeyAgent 和 AssociationAgent 已建立关联关系，
    召回时直接通过 edges 图关系拉取。
    topk: 每个 key 最多返回的主记忆条数。
    """
    try:
        items = []

        for key in candidate_keys:
            context = get_key_context(key)

            if not context["success"]:
                if context.get("error") == "KEY_NOT_FOUND":
                    items.append({"key": key, "key_not_found": True})
                continue

            key_items = context["items"]
            if not key_items:
                continue

            # 从 key_items 中收集该 key 下所有记忆的 fingerprint
            key_fps = [item["fingerprint"] for item in key_items]

            conn = get_db()

            # 1. 通过 recall_target 在 edges 中找到与该 key 记忆相关的关联记忆
            #    关联记忆可能是其他 key 下的（跨 key 关联）
            #    转义 SQL LIKE 特殊字符 % 和 _
            escaped_target = (
                recall_target.replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            like_pattern = f"%{escaped_target}%"
            matched_fps = []
            matched_fp_data = {}  # {fp: {weight, strength}}
            for fp in key_fps:
                # 查找与 fp 关联的记忆，且该记忆的 tag 或 memory 包含 recall_target
                edge_rows = conn.execute(
                    """SELECT DISTINCT e.from_fingerprint, e.to_fingerprint, e.effective_strength,
                                  m.fingerprint, m.tag, m.memory, m.base_score as weight
                           FROM edges e
                           JOIN memory m ON (e.from_fingerprint = m.fingerprint OR e.to_fingerprint = m.fingerprint)
                           WHERE (e.from_fingerprint = ? OR e.to_fingerprint = ?)
                             AND m.fingerprint != ?
                             AND (m.tag LIKE ? ESCAPE '\\' OR m.memory LIKE ? ESCAPE '\\')
                           ORDER BY e.effective_strength DESC""",
                    (fp, fp, fp, like_pattern, like_pattern),
                ).fetchall()

                for row in edge_rows:
                    other_fp = (
                        row["from_fingerprint"]
                        if row["to_fingerprint"] == fp
                        else row["to_fingerprint"]
                    )
                    if other_fp not in matched_fps:
                        matched_fps.append(other_fp)
                        matched_fp_data[other_fp] = {
                            "weight": row["weight"]
                            if row["weight"] is not None
                            else 0.5,
                            "effective_strength": row["effective_strength"],
                        }

            # 2. 如果 recall_target 没有直接匹配到关联，用 edges 扩展 key_fps 自身
            if not matched_fps:
                # 遍历该 key 下所有记忆，通过 edges 找到关联记忆
                for fp in key_fps:
                    edge_rows = conn.execute(
                        """SELECT e.from_fingerprint, e.to_fingerprint, e.effective_strength,
                                  m.fingerprint, m.tag, m.memory, m.base_score as weight
                           FROM edges e
                           JOIN memory m ON (e.from_fingerprint = m.fingerprint OR e.to_fingerprint = m.fingerprint)
                           WHERE (e.from_fingerprint = ? OR e.to_fingerprint = ?)
                             AND m.fingerprint != ?
                           ORDER BY e.effective_strength DESC""",
                        (fp, fp, fp),
                    ).fetchall()

                    for row in edge_rows:
                        other_fp = (
                            row["from_fingerprint"]
                            if row["to_fingerprint"] == fp
                            else row["to_fingerprint"]
                        )
                        # 关联记忆不在当前 key 中（跨 key 关联）
                        if other_fp not in key_fps and other_fp not in matched_fps:
                            matched_fps.append(other_fp)
                            matched_fp_data[other_fp] = {
                                "weight": row["weight"]
                                if row["weight"] is not None
                                else 0.5,
                                "effective_strength": row["effective_strength"],
                            }

            # 按 effective_strength 降序排列，截取 topk
            matched_fps.sort(
                key=lambda fp: matched_fp_data.get(fp, {}).get("effective_strength", 0),
                reverse=True,
            )
            matched_fps = matched_fps[:topk]

            # 3. 通过 edges 扩展 matched_fps，找到关联的关联
            #    每个 main_fp 最多扩展 topk 条 associated，避免图爆炸
            associated_fps = {}
            for fp in matched_fps:
                edge_rows = conn.execute(
                    """SELECT e.from_fingerprint, e.to_fingerprint, e.effective_strength, m.base_score as weight
                       FROM edges e
                       JOIN memory m ON (e.from_fingerprint = m.fingerprint OR e.to_fingerprint = m.fingerprint)
                       WHERE (e.from_fingerprint = ? OR e.to_fingerprint = ?)
                         AND m.fingerprint != ?
                       ORDER BY e.effective_strength DESC
                       LIMIT ?""",
                    (fp, fp, fp, topk),
                ).fetchall()

                fps = []
                for edge in edge_rows:
                    other_fp = (
                        edge["to_fingerprint"]
                        if edge["from_fingerprint"] == fp
                        else edge["from_fingerprint"]
                    )
                    if other_fp not in fps:
                        fps.append(
                            {
                                "fingerprint": other_fp,
                                "weight": edge["weight"]
                                if edge["weight"] is not None
                                else 0.5,
                                "effective_strength": edge["effective_strength"],
                            }
                        )

                associated_fps[fp] = fps

            conn.close()

            # 构建带权重的main_fingerprints列表
            main_fp_list = []
            for fp in matched_fps:
                data = matched_fp_data.get(
                    fp, {"weight": 0.5, "effective_strength": 0.5}
                )
                main_fp_list.append(
                    {
                        "fingerprint": fp,
                        "weight": data["weight"],
                        "effective_strength": data["effective_strength"],
                    }
                )

            items.append(
                {
                    "key": key,
                    "main_fingerprints": main_fp_list,
                    "associated_fingerprints": associated_fps,
                }
            )

        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "error": str(e)}


def request_memory_recall(
    recall_mode: str,
    normalized_user_request: str,
    recall_target: str,
    candidate_keys: list[str],
    time_scope: dict | None,
    topk: int = 2,
) -> dict:
    try:
        request_id = f"req_{uuid.uuid4().hex[:8]}"

        if recall_mode == "explicit" and time_scope is not None:
            result = query_sub_by_time(time_scope["start"], time_scope["end"])
            return {
                "success": True,
                "request_id": request_id,
                "recall_mode": recall_mode,
                "dispatch_strategy": "time_query",
                "topk": topk,
                "time_query_result": result,
            }

        if not candidate_keys:
            overview = get_key_overview()
            if overview["success"]:
                candidate_keys = [k["key"] for k in overview["keys"]]

        dispatch_result = dispatch_recall_to_keys(
            candidate_keys, normalized_user_request, recall_target, topk
        )

        return {
            "success": True,
            "request_id": request_id,
            "recall_mode": recall_mode,
            "dispatch_strategy": "semantic_routing",
            "topk": topk,
            "dispatch_result": dispatch_result,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

import os
import json
from src.tools.memory_tools import get_db
from src.tools.key_tools import get_current_keys_dir


def get_memory_by_fingerprint(fingerprints: list[str]) -> dict:
    """查询记忆原文，返回结构化数据供系统使用"""
    try:
        if not fingerprints:
            return {"success": True, "items": []}

        conn = get_db()
        placeholders = ",".join(["?"] * len(fingerprints))
        rows = conn.execute(
            f"SELECT fingerprint, key, memory, tag, created_at FROM memory WHERE fingerprint IN ({placeholders})",
            fingerprints,
        ).fetchall()
        conn.close()

        found_map = {}
        for row in rows:
            d = dict(row)
            found_map[d["fingerprint"]] = d

        items = []
        for fp in fingerprints:
            if fp in found_map:
                row = found_map[fp]
                items.append(
                    {
                        "fingerprint": fp,
                        "found": True,
                        "memory": row["memory"],
                        "key": row["key"],
                        "tag": row["tag"],
                        "created_at": row["created_at"],
                    }
                )
            else:
                items.append(
                    {
                        "fingerprint": fp,
                        "found": False,
                        "memory": None,
                    }
                )

        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "error": str(e)}


def format_memory_for_agent(fingerprints: list[str]) -> str:
    """格式化记忆为清晰的文本格式供模型阅读：每行一个 tag-指纹:记忆"""
    result = get_memory_by_fingerprint(fingerprints)
    if not result.get("success"):
        return f"查询失败: {result.get('error')}"

    lines = []
    for item in result.get("items", []):
        fp = item.get("fingerprint", "")
        if item.get("found"):
            tag = item.get("tag", "")
            memory = item.get("memory", "")
            lines.append(f"{tag}-{fp}:{memory}")
        else:
            lines.append(f"未知-{fp}:未找到记忆")

    return "\n".join(lines)


def get_key_context(key: str) -> dict:
    try:
        keys_dir = get_current_keys_dir()
        summary_file = os.path.join(keys_dir, key, "summary.json")

        if not os.path.isdir(os.path.join(keys_dir, key)):
            return {"success": False, "error": "KEY_NOT_FOUND"}

        summary = ""
        if os.path.exists(summary_file):
            with open(summary_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                summary = data.get("summary", "")

        conn = get_db()
        rows = conn.execute(
            "SELECT fingerprint, tag FROM memory WHERE key = ? ORDER BY created_at DESC",
            (key,),
        ).fetchall()
        conn.close()

        items = [{"fingerprint": row["fingerprint"], "tag": row["tag"]} for row in rows]

        return {"success": True, "key": key, "summary": summary, "items": items}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_cross_key_context(main_fingerprint: str) -> dict:
    try:
        conn = get_db()

        main_row = conn.execute(
            "SELECT fingerprint, memory, key FROM memory WHERE fingerprint = ?",
            (main_fingerprint,),
        ).fetchone()

        if not main_row:
            conn.close()
            return {"success": False, "error": "FP_NOT_FOUND"}

        main_key = main_row["key"]

        edge_rows = conn.execute(
            "SELECT from_fingerprint, to_fingerprint FROM edges WHERE from_fingerprint = ? OR to_fingerprint = ?",
            (main_fingerprint, main_fingerprint),
        ).fetchall()

        existing_fps = set()
        for edge in edge_rows:
            if edge["from_fingerprint"] != main_fingerprint:
                existing_fps.add(edge["from_fingerprint"])
            if edge["to_fingerprint"] != main_fingerprint:
                existing_fps.add(edge["to_fingerprint"])

        candidate_rows = conn.execute(
            "SELECT fingerprint, tag, memory FROM memory WHERE key != ? ORDER BY created_at DESC LIMIT 100",
            (main_key,),
        ).fetchall()
        conn.close()

        candidates = []
        for row in candidate_rows:
            fp = row["fingerprint"]
            if fp != main_fingerprint and fp not in existing_fps:
                candidates.append(
                    {"fingerprint": fp, "tag": row["tag"], "memory": row["memory"]}
                )

        return {
            "success": True,
            "main_memory": {
                "fingerprint": main_row["fingerprint"],
                "memory": main_row["memory"],
                "key": main_row["key"],
            },
            "candidates": candidates,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

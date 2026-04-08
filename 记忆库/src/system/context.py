import json


def assemble_context(
    history: str,
    system_prompt: str,
    recall_blocks: list | str,
    current_message: str,
    queue_messages: list = None,
    memory_space: str = None,
) -> str:
    """装配五块上下文"""
    if queue_messages is None:
        queue_messages = []

    # 解析recall_blocks
    if isinstance(recall_blocks, str):
        try:
            recall_blocks = json.loads(recall_blocks)
        except json.JSONDecodeError:
            recall_blocks = []

    # 格式化记忆召回区块
    recall_section = format_recall_blocks(recall_blocks)

    # 合并排队区消息到本轮对话消息
    message_section = current_message
    if queue_messages:
        queue_text = "\n".join(queue_messages)
        message_section = f"{queue_text}\n{current_message}"

    # 装配五块上下文
    parts = []

    if history:
        parts.append(f"<历史消息>\n{history}\n</历史消息>")

    if system_prompt:
        parts.append(f"<系统提示词>\n{system_prompt}\n</系统提示词>")

    if memory_space:
        parts.append(f"<记忆空间>\n{memory_space}\n</记忆空间>")

    if recall_section:
        parts.append(f"<记忆召回>\n{recall_section}\n</记忆召回>")

    parts.append(f"<本轮对话消息>\n{message_section}\n</本轮对话消息>")

    return "\n\n".join(parts)


def format_recall_blocks(recall_blocks: list) -> str:
    """格式化recall_blocks为记忆召回区块"""
    if not recall_blocks:
        return ""

    lines = []
    for i, block in enumerate(recall_blocks, 1):
        key = block.get("key", "")
        time = block.get("time", "")
        memory = block.get("memory", "")
        fingerprint = block.get("fingerprint", "")

        lines.append(f"[{i}]")
        lines.append(f"key: {key}")
        lines.append(f"time: {time}")
        lines.append(f"fingerprint: {fingerprint}")
        lines.append(f"memory: {memory}")
        lines.append("")

    return "\n".join(lines).strip()


def get_assembly_status() -> dict:
    """获取装配状态"""
    return {
        "available": True,
        "components": ["history", "system_prompt", "recall", "message"],
    }

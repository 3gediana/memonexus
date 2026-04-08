"""
会话工具 - 管理会话文件
"""

import json
import os
from src.system.config import get_current_instance_config


def get_session_file_path() -> str:
    """获取当前实例的会话文件路径"""
    instance = get_current_instance_config()
    data_dir = os.path.dirname(instance["db_path"])
    return os.path.join(data_dir, "current_session.json")


def load_session() -> list:
    """加载会话消息"""
    session_file = get_session_file_path()
    if not os.path.exists(session_file):
        return []

    try:
        with open(session_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        return []


def save_session(messages: list) -> dict:
    """保存会话消息"""
    try:
        session_file = get_session_file_path()
        os.makedirs(os.path.dirname(session_file), exist_ok=True)

        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def append_to_session(message: str, turn_index: int) -> dict:
    """追加消息到会话"""
    messages = load_session()
    messages.append(
        {
            "message": message,
            "turn_index": turn_index,
        }
    )
    return save_session(messages)


def clear_session() -> dict:
    """清空会话"""
    return save_session([])


def get_session_messages() -> list:
    """获取会话中的所有消息"""
    return load_session()

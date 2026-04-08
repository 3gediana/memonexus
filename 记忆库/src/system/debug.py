"""
调试工具 - 打印模型调用信息
"""

import json
import os
from functools import wraps

# 调试模式开关
DEBUG_MODE = os.environ.get("MEMORY_DEBUG", "0") == "1"


def set_debug_mode(enabled: bool):
    """设置调试模式"""
    global DEBUG_MODE
    DEBUG_MODE = enabled


def debug_print(title: str, data):
    """调试打印"""
    if not DEBUG_MODE:
        return

    print("\n" + "=" * 60)
    print(f"[DEBUG] {title}")
    print("=" * 60)

    if isinstance(data, (dict, list)):
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(data)
    print("=" * 60 + "\n")


def debug_tool_call(tool_name: str, params: dict = None, result=None):
    """工具调用打印"""
    if not DEBUG_MODE:
        return

    print(f"\n{'-' * 40}")
    print(f"[TOOL] {tool_name}")
    print(f"{'-' * 40}")

    if params:
        print(f"[PARAMS]:")
        print(json.dumps(params, ensure_ascii=False, indent=2))

    if result is not None:
        print(f"[RESULT]:")
        if isinstance(result, (dict, list)):
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result)

    print(f"{'-' * 40}\n")


def debug_llm_response(agent_name: str, tool_calls: list = None, content: str = None):
    """LLM响应打印"""
    if not DEBUG_MODE:
        return

    print(f"\n{'=' * 60}")
    print(f"[LLM] {agent_name} 响应")
    print(f"{'=' * 60}")

    if tool_calls:
        print(f"\n[TOOL_CALLS]:")
        for tc in tool_calls:
            print(f"  - {tc.get('name', 'unknown')}: {tc.get('arguments', {})}")

    if content:
        print(f"\n[CONTENT]: {content}")

    print(f"{'=' * 60}\n")

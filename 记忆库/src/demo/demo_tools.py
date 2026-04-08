"""
演示工具包装器 - 封装 CLI 功能供 SimUser Agent 调用
"""

import json
import time
import subprocess
import sys
import os

# 确保能导入项目模块
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from src.tools.session_tools import (
    clear_session,
    get_session_messages,
    append_to_session,
    save_session,
)
from src.system.storage_flow import process_user_message
from src.system.main import handle_user_message
from src.tools.key_tools import get_key_overview, list_key_dirs
from src.tools.memory_tools import list_memory_by_key
from src.system.config import (
    create_instance,
    list_instances,
    switch_instance,
    get_current_instance_config,
)
from src.db.init import init_database, init_sub_database
from src.tools.key_tools import init_keys_directory


class DemoTools:
    """演示工具集"""

    def __init__(self, log_callback=None):
        self.log_callback = log_callback
        self.turn_index = 0

    def _log(self, tool_name: str, params: dict, result: dict):
        if self.log_callback:
            self.log_callback(tool_name, params, result)

    def chat(self, message: str) -> dict:
        """发送消息给AI"""
        self.turn_index += 1
        self._log(
            "chat", {"message": message, "turn": self.turn_index}, {"status": "sending"}
        )
        result = handle_user_message(message, self.turn_index)

        output = {
            "success": result.get("success", False),
            "reply": result.get("content", ""),
            "has_recalled": result.get("has_recalled", False),
            "pending_hits": result.get("pending_hits", []),
        }
        self._log("chat", {"message": message}, output)
        return output

    def new_session(self) -> dict:
        """开启新会话"""
        result = clear_session()
        self.turn_index = 0
        output = {"success": result.get("success", False), "turn_reset": True}
        self._log("new_session", {}, output)
        return output

    def store_memories(self) -> dict:
        """手动触发记忆存储"""
        messages = get_session_messages()
        if not messages:
            output = {"success": True, "stored": 0, "message": "没有待存储的消息"}
            self._log("store_memories", {}, output)
            return output

        stored = 0
        failed = 0
        details = []
        for item in messages:
            msg = item["message"]
            turn = item["turn_index"]
            result = process_user_message(msg, turn)
            if result.get("success"):
                stored += 1
                details.append({"message": msg[:50], "status": "ok"})
            else:
                failed += 1
                details.append(
                    {
                        "message": msg[:50],
                        "status": "failed",
                        "error": result.get("error"),
                    }
                )
            time.sleep(1)

        clear_session()
        output = {
            "success": True,
            "stored": stored,
            "failed": failed,
            "details": details,
        }
        self._log("store_memories", {}, output)
        return output

    def sleep(self, seconds: int) -> dict:
        """休眠指定秒数，超过45秒自动触发存储"""
        self._log("sleep", {"seconds": seconds}, {"status": f"sleeping for {seconds}s"})
        time.sleep(seconds)

        # 超过45秒，自动触发存储
        output = {"success": True, "slept": seconds, "auto_stored": False}
        if seconds >= 45:
            messages = get_session_messages()
            if messages:
                stored = 0
                for item in messages:
                    result = process_user_message(item["message"], item["turn_index"])
                    if result.get("success"):
                        stored += 1
                    time.sleep(1)
                clear_session()
                output["auto_stored"] = True
                output["auto_stored_count"] = stored
                self._log("sleep_auto_store", {}, {"stored": stored})

        self._log("sleep", {"seconds": seconds}, output)
        return output

    def view_key_overview(self) -> dict:
        """查看记忆分类概览"""
        result = get_key_overview(include_summary=False)
        output = {
            "success": result.get("success", False),
            "keys": result.get("keys", []),
        }
        self._log("view_key_overview", {}, output)
        return output

    def view_memories(self, key: str) -> dict:
        """查看某分类下的记忆"""
        result = list_memory_by_key(key)
        output = {
            "success": result.get("success", False),
            "count": len(result.get("memories", [])),
            "memories": [
                {
                    "fingerprint": m["fingerprint"],
                    "tag": m["tag"],
                    "memory": m["memory"],
                }
                for m in result.get("memories", [])
            ],
        }
        self._log("view_memories", {"key": key}, output)
        return output

    def switch_instance(self, name: str) -> dict:
        """切换实例"""
        result = switch_instance(name)
        if result.get("success"):
            self.turn_index = 0
        output = {
            "success": result.get("success", False),
            "message": result.get("message", result.get("error", "")),
        }
        self._log("switch_instance", {"name": name}, output)
        return output

    def create_instance(self, name: str) -> dict:
        """创建新实例"""
        result = create_instance(name)
        if result.get("success"):
            # 初始化数据库
            instance_config = result["instance"]
            init_database(instance_config["db_path"])
            init_sub_database(instance_config["sub_db_path"])
            init_keys_directory(instance_config["keys_dir"])
        output = {
            "success": result.get("success", False),
            "message": result.get("message", result.get("error", "")),
        }
        self._log("create_instance", {"name": name}, output)
        return output

    def list_instances(self) -> dict:
        """列出所有实例"""
        result = list_instances()
        output = {
            "current_instance": result.get("current_instance"),
            "instances": list(result.get("instances", {}).keys()),
        }
        self._log("list_instances", {}, output)
        return output

    def finish_demo(self) -> dict:
        """结束演示"""
        output = {"success": True, "message": "演示结束"}
        self._log("finish_demo", {}, output)
        return output

    def cleanup_demo(self, instance_name: str) -> dict:
        """清理演示产生的垃圾"""
        import shutil
        from src.system.config import get_current_instance_config, switch_instance

        output = {"success": True, "cleaned": []}

        # 1. 删除演示实例的数据目录
        from src.system.config import get_config

        config = get_config()
        instance = config.get("instances", {}).get(instance_name)
        if instance:
            db_path = instance.get("db_path", "")
            if db_path:
                data_dir = os.path.dirname(db_path)
                if os.path.exists(data_dir):
                    shutil.rmtree(data_dir)
                    output["cleaned"].append(f"数据目录: {data_dir}")

            # 2. 从 config 中删除实例记录
            del config["instances"][instance_name]
            config_path = os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                ),
                "config.json",
            )
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            output["cleaned"].append(f"config.json 中移除实例: {instance_name}")

        # 3. 清空当前实例的 session
        clear_session()
        output["cleaned"].append("session 已清空")

        self._log("cleanup_demo", {"instance_name": instance_name}, output)
        return output

    def execute(self, tool_name: str, args: dict) -> dict:
        """统一执行入口"""
        handler = getattr(self, tool_name, None)
        if handler:
            return handler(**args)
        return {"success": False, "error": f"Unknown tool: {tool_name}"}

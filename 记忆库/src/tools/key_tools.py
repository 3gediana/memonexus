import os
import json
import sqlite3
from src.system.config import get_current_instance_config
from src.system.fingerprint import get_utc_now

BUILT_IN_KEYS = [
    "preference",
    "schedule",
    "work",
    "study",
    "health",
    "emotion",
    "relationship",
    "project",
    "code",
]


def get_current_keys_dir() -> str:
    instance = get_current_instance_config()
    return instance["keys_dir"]


def list_all_keys(keys_dir: str = None) -> list[str]:
    if keys_dir is None:
        keys_dir = get_current_keys_dir()

    all_keys = BUILT_IN_KEYS.copy()
    if os.path.exists(keys_dir):
        for item in os.listdir(keys_dir):
            item_path = os.path.join(keys_dir, item)
            if os.path.isdir(item_path) and item not in all_keys:
                all_keys.append(item)
    return all_keys


def init_keys_directory(keys_dir: str = None) -> dict:
    try:
        if keys_dir is None:
            keys_dir = get_current_keys_dir()

        for key_name in BUILT_IN_KEYS:
            key_path = os.path.join(keys_dir, key_name)
            os.makedirs(key_path, exist_ok=True)

            summary_file = os.path.join(key_path, "summary.json")
            if not os.path.exists(summary_file):
                data = {"summary": "", "updated_at": get_utc_now()}
                with open(summary_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_key_dirs(keys_dir: str = None) -> dict:
    try:
        if keys_dir is None:
            keys_dir = get_current_keys_dir()

        dirs = []
        for key_name in BUILT_IN_KEYS:
            dirs.append(f"{key_name}/summary.json")

        return {"success": True, "keys_dir": keys_dir, "dirs": dirs}
    except Exception as e:
        return {"success": False, "error": str(e)}


def create_key(key_name: str, keys_dir: str = None) -> dict:
    try:
        if keys_dir is None:
            keys_dir = get_current_keys_dir()

        if not key_name.islower() or not key_name.replace("_", "").isalnum():
            return {"success": False, "error": "INVALID_KEY_NAME"}

        key_path = os.path.join(keys_dir, key_name)
        if os.path.exists(key_path):
            return {"success": True, "key": key_name, "created": False}

        os.makedirs(key_path, exist_ok=True)

        summary_file = os.path.join(key_path, "summary.json")
        data = {"summary": "", "updated_at": get_utc_now()}
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return {"success": True, "key": key_name, "created": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_key_overview(keys_dir: str = None, include_summary: bool = True) -> dict:
    try:
        if keys_dir is None:
            keys_dir = get_current_keys_dir()

        all_keys = list_all_keys(keys_dir)
        instance = get_current_instance_config()
        db_path = instance["db_path"]

        result_keys = []
        conn = sqlite3.connect(db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        try:
            for key_name in all_keys:
                key_path = os.path.join(keys_dir, key_name)
                if os.path.isdir(key_path):
                    cursor = conn.execute(
                        "SELECT COUNT(*) FROM memory WHERE key = ?", (key_name,)
                    )
                    count = cursor.fetchone()[0]

                    if include_summary:
                        summary_file = os.path.join(key_path, "summary.json")
                        if os.path.exists(summary_file):
                            with open(summary_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                                result_keys.append(
                                    {
                                        "key": key_name,
                                        "summary": data.get("summary", ""),
                                        "memory_count": count,
                                    }
                                )
                        else:
                            result_keys.append(
                                {
                                    "key": key_name,
                                    "summary": "",
                                    "memory_count": count,
                                }
                            )
                    else:
                        result_keys.append({"key": key_name, "memory_count": count})
        finally:
            conn.close()

        return {"success": True, "keys": result_keys}
    except Exception as e:
        return {"success": False, "error": str(e)}

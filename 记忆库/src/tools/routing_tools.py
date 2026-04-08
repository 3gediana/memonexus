import os
from src.tools.key_tools import get_current_keys_dir


def _key_exists(key: str) -> bool:
    keys_dir = get_current_keys_dir()
    key_path = os.path.join(keys_dir, key)
    return os.path.isdir(key_path)


def assign_memory_to_keys(items: list[dict]) -> dict:
    try:
        accepted = []
        rejected = []

        for item in items:
            key = item["target_key"]
            if _key_exists(key):
                accepted.append(item)
            else:
                rejected.append({**item, "reason": "KEY_NOT_FOUND"})

        return {"success": True, "accepted": accepted, "rejected": rejected}
    except Exception as e:
        return {"success": False, "error": str(e)}

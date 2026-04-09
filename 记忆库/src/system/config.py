import json
import os
from copy import deepcopy

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config.json"
)

_config_cache = None
_config_mtime = 0


def load_config() -> dict:
    global _config_cache, _config_mtime
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
        if _config_cache is not None and mtime == _config_mtime:
            return deepcopy(_config_cache)
    except OSError:
        if _config_cache is not None:
            return deepcopy(_config_cache)

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        _config_cache = json.load(f)
    _config_mtime = os.path.getmtime(CONFIG_PATH)
    return deepcopy(_config_cache)


def save_config(config: dict) -> None:
    global _config_cache, _config_mtime
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    _config_cache = None
    _config_mtime = 0


def get_current_instance_config() -> dict:
    config = load_config()
    return config["instances"][config["current_instance"]]


def list_instances() -> dict:
    config = load_config()
    return {
        "current_instance": config["current_instance"],
        "instances": config.get("instances", {}),
    }


def switch_instance(name: str) -> dict:
    config = load_config()
    if name not in config.get("instances", {}):
        return {"success": False, "error": "INSTANCE_NOT_FOUND"}
    config["current_instance"] = name
    save_config(config)
    return {"success": True, "current_instance": name}


def create_instance(name: str) -> dict:
    config = load_config()
    instances = config.setdefault("instances", {})
    if name in instances:
        return {"success": False, "error": "INSTANCE_ALREADY_EXISTS"}

    base_instance_name = config.get("current_instance") or next(iter(instances.keys()))
    if not base_instance_name or base_instance_name not in instances:
        return {"success": False, "error": "BASE_INSTANCE_NOT_FOUND"}

    template = deepcopy(instances[base_instance_name])
    template["db_path"] = f"instances/{name}/memories.db"
    template["sub_db_path"] = f"instances/{name}/sub.db"
    template["keys_dir"] = f"instances/{name}/keys"
    instances[name] = template
    save_config(config)
    return {"success": True, "instance": {"name": name, **template}}

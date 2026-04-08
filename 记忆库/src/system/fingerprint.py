import hashlib
from datetime import datetime, timezone


def generate_fingerprint(memory_text: str) -> str:
    hash_bytes = hashlib.sha256(memory_text.encode("utf-8")).digest()
    hash_hex = hash_bytes.hex()[:16]
    return f"fp_{hash_hex}"


def get_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

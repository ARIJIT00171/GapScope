import json
import time
from pathlib import Path

CACHE_FILE = Path(__file__).parent / "cache.json"
TTL_SECONDS = 7 * 24 * 60 * 60


def _load() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: dict) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def get(key: str):
    data = _load()
    entry = data.get(key)
    if entry is None:
        return None
    if time.time() - entry.get("saved_at", 0) > TTL_SECONDS:
        return None
    return entry.get("value")


def set(key: str, value) -> None:
    data = _load()
    data[key] = {"value": value, "saved_at": time.time()}
    _save(data)

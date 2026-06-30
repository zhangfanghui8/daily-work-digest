from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.paths import project_root, raw_dir

STATUS_OK = "ok"
STATUS_EMPTY = "empty"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_NOT_COLLECTED = "not_collected"

STATUS_FILE = "_collection_status.json"


def status_path(date_str: str) -> Path:
    return raw_dir(date_str) / STATUS_FILE


def empty_status_store(date_str: str) -> dict[str, Any]:
    return {"date": date_str, "channels": {}}


def load_status(date_str: str) -> dict[str, Any]:
    path = status_path(date_str)
    if not path.is_file():
        return empty_status_store(date_str)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("channels", {})
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return empty_status_store(date_str)


def save_status(date_str: str, store: dict[str, Any]) -> Path:
    path = status_path(date_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def record_channel(
    store: dict[str, Any],
    channel_id: str,
    *,
    status: str,
    entry_count: int = 0,
    message: str = "",
) -> None:
    store.setdefault("channels", {})[channel_id] = {
        "status": status,
        "entry_count": entry_count,
        "message": message.strip(),
    }


def infer_status_from_raw(channel_id: str, raw: dict[str, Any]) -> tuple[str, int]:
    from .channel_registry import CHANNEL_BY_ID

    channel = CHANNEL_BY_ID.get(channel_id)
    if not channel:
        return STATUS_OK, 0
    count = channel.count_entries(raw)
    return (STATUS_OK if count > 0 else STATUS_EMPTY), count

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from .paths import project_root


DEFAULT_CONFIG: dict[str, Any] = {
    "timezone": "Asia/Shanghai",
    "git": {
        "repos": [],
        "author_email": "",
        "exclude_merges": True,
        "exclude_patterns": ["^Merge ", "^wip", "^WIP"],
    },
    "manual": {"enabled": True},
    "tags": {
        "commit_fix": ["开发", "bugfix"],
        "commit_feat": ["开发", "功能"],
        "commit_docs": ["文档"],
        "commit_refactor": ["开发", "重构"],
        "manual_meeting": ["会议", "协作"],
        "manual_default": ["协作"],
        "calendar_meeting": ["会议", "协作"],
    },
    "wecom": {
        "enabled": False,
        "caldav": {
            "server": "https://caldav.wecom.work",
            "username": "",
            "password": "",
            "calendar_id": "",
        },
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    root = project_root()
    path = config_path or root / "config.yaml"
    example = root / "config.example.yaml"

    if path.is_file():
        with path.open(encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        return _deep_merge(DEFAULT_CONFIG, user_cfg)

    if example.is_file():
        with example.open(encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        return _deep_merge(DEFAULT_CONFIG, user_cfg)

    return copy.deepcopy(DEFAULT_CONFIG)

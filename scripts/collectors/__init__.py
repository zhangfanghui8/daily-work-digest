from __future__ import annotations

import json
from pathlib import Path
from typing import Type

from .base import BaseCollector
from .yuque_docs import YuqueDocsCollector
from .dingtalk_schedule import DingTalkScheduleCollector
from .feishu_chat import FeishuChatCollector
from .feishu_docs import FeishuDocsCollector
from .feishu_schedule import FeishuScheduleCollector
from .git import GitCollector
from .manual import ManualCollector
from .wecom_schedule import WeComScheduleCollector
from .zentao import ZenTaoCollector
from .jira import JiraCollector

# 注册所有采集器；新增渠道在此追加
ALL_COLLECTORS: list[Type[BaseCollector]] = [
    GitCollector,
    ManualCollector,
    WeComScheduleCollector,
    FeishuScheduleCollector,
    FeishuChatCollector,
    FeishuDocsCollector,
    YuqueDocsCollector,
    DingTalkScheduleCollector,
    ZenTaoCollector,
    JiraCollector,
]

__all__ = [
    "BaseCollector",
    "GitCollector",
    "ManualCollector",
    "WeComScheduleCollector",
    "FeishuScheduleCollector",
    "FeishuChatCollector",
    "FeishuDocsCollector",
    "YuqueDocsCollector",
    "DingTalkScheduleCollector",
    "ZenTaoCollector",
    "JiraCollector",
    "ALL_COLLECTORS",
    "get_enabled_collectors",
    "run_collectors",
]


def get_enabled_collectors(
    config: dict,
    sources: list[str] | None = None,
    config_path: Path | None = None,
) -> list[BaseCollector]:
    """返回已启用且匹配 sources 过滤的采集器实例。"""
    normalized = {s.lower() for s in sources} if sources else None
    instances: list[BaseCollector] = []

    for collector_cls in ALL_COLLECTORS:
        name = collector_cls.source_name()
        if normalized is not None and name not in normalized:
            continue
        if not collector_cls.is_enabled(config):
            continue
        instances.append(collector_cls(config, config_path))

    return instances


def run_collectors(
    date_str: str,
    config_path: Path | None = None,
    sources: list[str] | None = None,
) -> list[Path]:
    """运行 L1 采集，返回各渠道 raw 文件路径；失败不中断，写入 _collection_status.json。"""
    from utils.config_loader import load_config
    from utils.paths import ensure_data_dirs

    from .channel_registry import CHANNEL_BY_COLLECTOR
    from .collection_status import (
        STATUS_EMPTY,
        STATUS_FAILED,
        STATUS_OK,
        STATUS_SKIPPED,
        load_status,
        record_channel,
        save_status,
    )

    config = load_config(config_path)
    normalized = {s.lower() for s in sources} if sources else None
    ensure_data_dirs(date_str)
    status_store = load_status(date_str)
    status_store["date"] = date_str

    outputs: list[Path] = []

    for collector_cls in ALL_COLLECTORS:
        name = collector_cls.source_name()
        channel = CHANNEL_BY_COLLECTOR.get(name)
        channel_id = channel.id if channel else name

        if normalized is not None and name not in normalized:
            continue

        if not collector_cls.is_enabled(config):
            record_channel(
                status_store,
                channel_id,
                status=STATUS_SKIPPED,
                message="未启用或未配置",
            )
            continue

        collector = collector_cls(config, config_path)
        print(f"[{name}] 采集中…")
        try:
            out_path = collector.run(date_str)
            outputs.append(out_path)
            raw = json.loads(out_path.read_text(encoding="utf-8"))
            count = channel.count_entries(raw) if channel else len(raw.get("entries") or [])
            record_channel(
                status_store,
                channel_id,
                status=STATUS_OK if count > 0 else STATUS_EMPTY,
                entry_count=count,
                message="",
            )
        except Exception as exc:
            record_channel(
                status_store,
                channel_id,
                status=STATUS_FAILED,
                entry_count=0,
                message=str(exc).splitlines()[0][:200],
            )
            print(f"[{name}] 采集失败: {exc}")

    save_status(date_str, status_store)

    if not outputs and not status_store.get("channels"):
        print("警告: 没有可用的采集器（检查 config 或 --sources 参数）")

    return outputs

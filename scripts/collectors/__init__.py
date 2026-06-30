from __future__ import annotations

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
    """运行 L1 采集，返回各渠道 raw 文件路径。"""
    from utils.config_loader import load_config

    config = load_config(config_path)
    collectors = get_enabled_collectors(config, sources, config_path)

    if not collectors:
        print("警告: 没有可用的采集器（检查 config 或 --sources 参数）")
        return []

    outputs: list[Path] = []
    for collector in collectors:
        print(f"[{collector.source_name()}] 采集中…")
        outputs.append(collector.run(date_str))

    return outputs

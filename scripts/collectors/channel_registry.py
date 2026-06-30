from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ChannelDef:
    """采集渠道元数据：用于 digest 维度展示与状态汇总。"""

    id: str
    collector_name: str
    dimension: str
    label: str
    raw_file: str
    count_entries: Callable[[dict[str, Any]], int]


def _count_git(raw: dict[str, Any]) -> int:
    total = 0
    for repo in raw.get("repos") or []:
        if isinstance(repo, dict):
            total += len(repo.get("commits") or [])
    return total


def _count_list_entries(raw: dict[str, Any]) -> int:
    entries = raw.get("entries")
    return len(entries) if isinstance(entries, list) else 0


CHANNELS: tuple[ChannelDef, ...] = (
    ChannelDef("git", "git", "代码开发", "Git", "git.json", _count_git),
    ChannelDef("manual", "manual", "手动补记", "手动补记", "manual.json", _count_list_entries),
    ChannelDef("wecom", "wecom", "日程", "企微日程", "wecom_schedule.json", _count_list_entries),
    ChannelDef("feishu", "feishu", "日程", "飞书日程", "feishu_schedule.json", _count_list_entries),
    ChannelDef(
        "dingtalk",
        "dingtalk",
        "日程",
        "钉钉日程",
        "dingtalk_schedule.json",
        _count_list_entries,
    ),
    ChannelDef(
        "feishu_docs",
        "feishu_docs",
        "文档",
        "飞书文档",
        "feishu_docs.json",
        _count_list_entries,
    ),
    ChannelDef(
        "yuque_docs",
        "yuque_docs",
        "文档",
        "语雀",
        "yuque_docs.json",
        _count_list_entries,
    ),
    ChannelDef(
        "feishu_chat",
        "feishu_chat",
        "IM",
        "飞书 IM",
        "feishu_chat.json",
        _count_list_entries,
    ),
)

CHANNEL_BY_ID = {c.id: c for c in CHANNELS}
CHANNEL_BY_COLLECTOR = {c.collector_name: c for c in CHANNELS}

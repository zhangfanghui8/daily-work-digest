from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from utils.config_loader import load_config
from utils.date_utils import format_week_range, week_date_range
from utils.paths import digest_path, ensure_data_dirs, manual_path, project_root, raw_dir


def infer_commit_tags(message: str, tags_cfg: dict[str, Any]) -> list[str]:
    lower = message.lower()
    if lower.startswith("fix") or "fix:" in lower or "bugfix" in lower:
        return list(tags_cfg.get("commit_fix") or ["开发", "bugfix"])
    if lower.startswith("feat") or "feat:" in lower or "feature" in lower:
        return list(tags_cfg.get("commit_feat") or ["开发", "功能"])
    if lower.startswith("docs") or "docs:" in lower:
        return list(tags_cfg.get("commit_docs") or ["文档"])
    if lower.startswith("refactor") or "refactor:" in lower:
        return list(tags_cfg.get("commit_refactor") or ["开发", "重构"])
    return ["开发"]


def infer_manual_tags(text: str, tags_cfg: dict[str, Any]) -> list[str]:
    keywords = ("会议", "对齐", "评审", "review", "讨论", "同步")
    if any(k.lower() in text.lower() for k in keywords):
        return list(tags_cfg.get("manual_meeting") or ["会议", "协作"])
    return list(tags_cfg.get("manual_default") or ["协作"])


def extract_time_from_authored(authored_at: str) -> str:
    try:
        dt = datetime.strptime(authored_at[:19], "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%H:%M:%S")
    except ValueError:
        return "00:00:00"


def git_raw_to_events(git_raw: dict[str, Any], tags_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for repo_block in git_raw.get("repos") or []:
        repo = repo_block.get("repo") or ""
        repo_name = Path(repo).name
        for commit in repo_block.get("commits") or []:
            short_hash = (commit.get("hash") or "")[:7]
            message = commit.get("message") or ""
            files_changed = commit.get("files_changed") or 0
            insertions = commit.get("insertions") or 0
            deletions = commit.get("deletions") or 0
            detail = (
                f"repo: {repo_name}, branch: {commit.get('branch', '')}, "
                f"files: {files_changed}, +{insertions}/-{deletions}"
            )
            events.append(
                {
                    "id": f"git-{commit.get('hash', short_hash)}",
                    "time": extract_time_from_authored(commit.get("authored_at") or ""),
                    "source": "git",
                    "type": "commit",
                    "title": message,
                    "detail": detail,
                    "url": "",
                    "tags": infer_commit_tags(message, tags_cfg),
                    "raw": commit,
                }
            )
    return events


def manual_entries_to_events(
    entries: list[dict[str, Any]],
    tags_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for entry in entries:
        title = entry.get("title") or ""
        events.append(
            {
                "id": entry.get("id") or f"manual-{len(events)+1:03d}",
                "time": entry.get("time") or "12:00:00",
                "source": "manual",
                "type": "note",
                "title": title,
                "detail": "",
                "url": "",
                "tags": infer_manual_tags(title, tags_cfg),
                "raw": entry,
            }
        )
    return events


def wecom_schedule_to_events(
    raw: dict[str, Any],
    tags_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    default_tags = list(tags_cfg.get("calendar_meeting") or ["会议", "协作"])
    events: list[dict[str, Any]] = []
    for entry in raw.get("entries") or []:
        title = entry.get("title") or "无标题日程"
        events.append(
            {
                "id": f"wecom-{entry.get('id', len(events)+1)}",
                "time": entry.get("time") or "09:00:00",
                "source": "wecom",
                "type": "meeting",
                "title": title,
                "detail": entry.get("detail") or "",
                "url": "",
                "tags": list(default_tags),
                "raw": entry,
            }
        )
    return events


def feishu_schedule_to_events(
    raw: dict[str, Any],
    tags_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    default_tags = list(tags_cfg.get("calendar_meeting") or ["会议", "协作"])
    events: list[dict[str, Any]] = []
    for entry in raw.get("entries") or []:
        title = entry.get("title") or "无标题日程"
        events.append(
            {
                "id": f"feishu-{entry.get('id', len(events)+1)}",
                "time": entry.get("time") or "09:00:00",
                "source": "feishu",
                "type": "meeting",
                "title": title,
                "detail": entry.get("detail") or "",
                "url": "",
                "tags": list(default_tags),
                "raw": entry,
            }
        )
    return events


def feishu_chat_to_events(
    raw: dict[str, Any],
    tags_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    default_tags = list(tags_cfg.get("feishu_chat") or tags_cfg.get("manual_default") or ["协作", "沟通"])
    events: list[dict[str, Any]] = []
    for entry in raw.get("entries") or []:
        title = entry.get("title") or "飞书消息"
        events.append(
            {
                "id": f"feishu-chat-{entry.get('id', len(events)+1)}",
                "time": entry.get("time") or "12:00:00",
                "source": "feishu",
                "type": "chat",
                "title": title,
                "detail": entry.get("detail") or "",
                "url": "",
                "tags": list(default_tags),
                "raw": entry,
            }
        )
    return events


def feishu_docs_to_events(
    raw: dict[str, Any],
    tags_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    default_tags = list(tags_cfg.get("feishu_docs") or tags_cfg.get("commit_docs") or ["文档", "产出"])
    events: list[dict[str, Any]] = []
    for entry in raw.get("entries") or []:
        title = entry.get("title") or "飞书文档"
        events.append(
            {
                "id": f"feishu-doc-{entry.get('id', len(events)+1)}",
                "time": entry.get("time") or "12:00:00",
                "source": "feishu",
                "type": "document",
                "title": title,
                "detail": entry.get("detail") or "",
                "url": entry.get("url") or "",
                "tags": list(default_tags),
                "raw": entry,
            }
        )
    return events


def yuque_docs_to_events(
    raw: dict[str, Any],
    tags_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    default_tags = list(tags_cfg.get("yuque_docs") or tags_cfg.get("commit_docs") or ["文档", "产出"])
    events: list[dict[str, Any]] = []
    for entry in raw.get("entries") or []:
        title = entry.get("title") or "语雀文档"
        events.append(
            {
                "id": f"yuque-doc-{entry.get('id', len(events)+1)}",
                "time": entry.get("time") or "12:00:00",
                "source": "yuque",
                "type": "document",
                "title": title,
                "detail": entry.get("detail") or "",
                "url": entry.get("url") or "",
                "tags": list(default_tags),
                "raw": entry,
            }
        )
    return events


def dingtalk_schedule_to_events(
    raw: dict[str, Any],
    tags_cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    default_tags = list(tags_cfg.get("calendar_meeting") or ["会议", "协作"])
    events: list[dict[str, Any]] = []
    for entry in raw.get("entries") or []:
        title = entry.get("title") or "无标题日程"
        events.append(
            {
                "id": f"dingtalk-{entry.get('id', len(events)+1)}",
                "time": entry.get("time") or "09:00:00",
                "source": "dingtalk",
                "type": "meeting",
                "title": title,
                "detail": entry.get("detail") or "",
                "url": "",
                "tags": list(default_tags),
                "raw": entry,
            }
        )
    return events


def normalize_time_for_sort(value: str) -> str:
    if not value:
        return "00:00:00"
    parts = value.split(":")
    while len(parts) < 3:
        parts.append("00")
    return ":".join(parts[:3])


def dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for event in events:
        event_id = event.get("id") or ""
        if event_id in seen:
            continue
        seen.add(event_id)
        result.append(event)
    result.sort(key=lambda e: normalize_time_for_sort(str(e.get("time") or "")))
    return result


def build_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for event in events:
        for tag in event.get("tags") or []:
            counter[tag] += 1
    return {
        "total_events": len(events),
        "by_source": dict(Counter(e.get("source", "unknown") for e in events)),
        "by_tag": dict(counter),
    }


def build_channels(cfg: dict[str, Any], date_str: str) -> dict[str, Any]:
    """汇总各渠道采集状态，供 digest 与成文区分「失败 / 无数据 / 有数据」。"""
    from collectors import ALL_COLLECTORS
    from collectors.channel_registry import CHANNELS
    from collectors.collection_status import (
        STATUS_EMPTY,
        STATUS_FAILED,
        STATUS_NOT_COLLECTED,
        STATUS_OK,
        STATUS_SKIPPED,
        infer_status_from_raw,
        load_status,
    )

    enabled: dict[str, bool] = {
        cls.source_name(): cls.is_enabled(cfg) for cls in ALL_COLLECTORS
    }
    recorded = load_status(date_str).get("channels") or {}
    day_raw = raw_dir(date_str)
    channels: dict[str, Any] = {}

    for ch in CHANNELS:
        if not enabled.get(ch.collector_name, False):
            continue

        rec = recorded.get(ch.id)
        raw_path = day_raw / ch.raw_file

        if rec and rec.get("status") == STATUS_FAILED:
            channels[ch.id] = {
                "dimension": ch.dimension,
                "label": ch.label,
                "status": STATUS_FAILED,
                "entry_count": 0,
                "message": rec.get("message") or "采集失败",
            }
            continue

        if rec and rec.get("status") in (STATUS_OK, STATUS_EMPTY):
            channels[ch.id] = {
                "dimension": ch.dimension,
                "label": ch.label,
                "status": rec.get("status"),
                "entry_count": int(rec.get("entry_count") or 0),
                "message": rec.get("message") or "",
            }
            continue

        if raw_path.is_file():
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            status, count = infer_status_from_raw(ch.id, raw)
            channels[ch.id] = {
                "dimension": ch.dimension,
                "label": ch.label,
                "status": status,
                "entry_count": count,
                "message": "",
            }
            continue

        channels[ch.id] = {
            "dimension": ch.dimension,
            "label": ch.label,
            "status": STATUS_NOT_COLLECTED,
            "entry_count": 0,
            "message": "本次未运行采集",
        }

    return channels


def _should_load_channel_raw(channel_id: str, channels: dict[str, Any]) -> bool:
    from collectors.collection_status import STATUS_FAILED, STATUS_NOT_COLLECTED

    info = channels.get(channel_id)
    if not info:
        return True
    return info.get("status") not in (STATUS_FAILED, STATUS_NOT_COLLECTED)


def _load_raw_events(
    date_str: str,
    tags_cfg: dict[str, Any],
    channels: dict[str, Any],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    day_raw = raw_dir(date_str)

    git_file = day_raw / "git.json"
    if git_file.is_file() and _should_load_channel_raw("git", channels):
        events.extend(git_raw_to_events(json.loads(git_file.read_text(encoding="utf-8")), tags_cfg))
    elif not git_file.is_file():
        print(f"提示: 未找到 {git_file.relative_to(project_root())}，可先运行 collect_all.py")

    manual_file = day_raw / "manual.json"
    if manual_file.is_file() and _should_load_channel_raw("manual", channels):
        manual_raw = json.loads(manual_file.read_text(encoding="utf-8"))
        events.extend(manual_entries_to_events(manual_raw.get("entries") or [], tags_cfg))
    elif manual_path(date_str).is_file() and _should_load_channel_raw("manual", channels):
        from collectors.manual import ManualCollector

        entries = ManualCollector({}, None)._parse_markdown(manual_path(date_str))
        events.extend(manual_entries_to_events(entries, tags_cfg))

    wecom_file = day_raw / "wecom_schedule.json"
    if wecom_file.is_file() and _should_load_channel_raw("wecom", channels):
        wecom_raw = json.loads(wecom_file.read_text(encoding="utf-8"))
        events.extend(wecom_schedule_to_events(wecom_raw, tags_cfg))

    feishu_file = day_raw / "feishu_schedule.json"
    if feishu_file.is_file() and _should_load_channel_raw("feishu", channels):
        feishu_raw = json.loads(feishu_file.read_text(encoding="utf-8"))
        events.extend(feishu_schedule_to_events(feishu_raw, tags_cfg))

    feishu_chat_file = day_raw / "feishu_chat.json"
    if feishu_chat_file.is_file() and _should_load_channel_raw("feishu_chat", channels):
        feishu_chat_raw = json.loads(feishu_chat_file.read_text(encoding="utf-8"))
        events.extend(feishu_chat_to_events(feishu_chat_raw, tags_cfg))

    feishu_docs_file = day_raw / "feishu_docs.json"
    if feishu_docs_file.is_file() and _should_load_channel_raw("feishu_docs", channels):
        feishu_docs_raw = json.loads(feishu_docs_file.read_text(encoding="utf-8"))
        events.extend(feishu_docs_to_events(feishu_docs_raw, tags_cfg))

    yuque_docs_file = day_raw / "yuque_docs.json"
    if yuque_docs_file.is_file() and _should_load_channel_raw("yuque_docs", channels):
        yuque_docs_raw = json.loads(yuque_docs_file.read_text(encoding="utf-8"))
        events.extend(yuque_docs_to_events(yuque_docs_raw, tags_cfg))

    dingtalk_file = day_raw / "dingtalk_schedule.json"
    if dingtalk_file.is_file() and _should_load_channel_raw("dingtalk", channels):
        dingtalk_raw = json.loads(dingtalk_file.read_text(encoding="utf-8"))
        events.extend(dingtalk_schedule_to_events(dingtalk_raw, tags_cfg))

    return events


def merge_channel_status_for_week(daily_digests: list[dict[str, Any]]) -> dict[str, Any]:
    """合并周内各日渠道状态。"""
    from collectors.collection_status import STATUS_EMPTY, STATUS_FAILED, STATUS_OK

    merged: dict[str, Any] = {}

    for digest in daily_digests:
        day = digest.get("date") or ""
        for channel_id, info in (digest.get("channels") or {}).items():
            if channel_id not in merged:
                merged[channel_id] = {
                    "dimension": info.get("dimension"),
                    "label": info.get("label"),
                    "status": info.get("status"),
                    "entry_count": 0,
                    "message": "",
                    "by_date": {},
                }
            bucket = merged[channel_id]
            bucket["by_date"][day] = {
                "status": info.get("status"),
                "entry_count": info.get("entry_count", 0),
                "message": info.get("message", ""),
            }
            bucket["entry_count"] += int(info.get("entry_count") or 0)

            status = info.get("status")
            if status == STATUS_FAILED:
                bucket["status"] = STATUS_FAILED
                bucket["message"] = info.get("message") or bucket["message"]
            elif bucket["status"] != STATUS_FAILED and bucket["entry_count"] > 0:
                bucket["status"] = STATUS_OK
            elif bucket["status"] not in (STATUS_FAILED, STATUS_OK):
                bucket["status"] = STATUS_EMPTY

    return merged


def merge_daily(date_str: str, config_path: Path | None = None) -> Path:
    cfg = load_config(config_path)
    tags_cfg = cfg.get("tags") or {}
    timezone = cfg.get("timezone", "Asia/Shanghai")

    ensure_data_dirs(date_str)
    channels = build_channels(cfg, date_str)
    events = dedupe_events(_load_raw_events(date_str, tags_cfg, channels))

    digest = {
        "date": date_str,
        "timezone": timezone,
        "events": events,
        "channels": channels,
        "summary": build_summary(events),
    }

    out = digest_path(date_str)
    out.write_text(json.dumps(digest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入: {out.relative_to(project_root())}（{len(events)} 条事件）")
    return out


def merge_week(reference_date: str, config_path: Path | None = None) -> Path:
    from utils.date_utils import resolve_date

    cfg = load_config(config_path)
    timezone = cfg.get("timezone", "Asia/Shanghai")
    ref = resolve_date(reference_date, timezone)
    dates = week_date_range(ref)

    all_events: list[dict[str, Any]] = []
    missing_days: list[str] = []
    daily_digests: list[dict[str, Any]] = []

    for d in dates:
        day = d.isoformat()
        path = digest_path(day)
        if not path.is_file():
            missing_days.append(day)
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["date"] = day
        daily_digests.append(payload)
        for event in payload.get("events") or []:
            copied = dict(event)
            copied["date"] = day
            all_events.append(copied)

    week_digest = {
        "week_range": format_week_range(dates),
        "timezone": timezone,
        "dates": [d.isoformat() for d in dates],
        "missing_days": missing_days,
        "events": all_events,
        "channels": merge_channel_status_for_week(daily_digests),
        "summary": build_summary(all_events),
    }

    ensure_data_dirs(ref.isoformat())
    out = digest_path(f"week-{dates[0].isoformat()}")
    out.write_text(json.dumps(week_digest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入: {out.relative_to(project_root())}（{len(all_events)} 条事件）")
    if missing_days:
        print(f"缺少日 digest 的日期: {', '.join(missing_days)}")
    return out

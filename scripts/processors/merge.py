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


def _load_raw_events(date_str: str, tags_cfg: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    day_raw = raw_dir(date_str)

    git_file = day_raw / "git.json"
    if git_file.is_file():
        events.extend(git_raw_to_events(json.loads(git_file.read_text(encoding="utf-8")), tags_cfg))
    else:
        print(f"提示: 未找到 {git_file.relative_to(project_root())}，可先运行 collect_all.py")

    manual_file = day_raw / "manual.json"
    if manual_file.is_file():
        manual_raw = json.loads(manual_file.read_text(encoding="utf-8"))
        events.extend(manual_entries_to_events(manual_raw.get("entries") or [], tags_cfg))
    elif manual_path(date_str).is_file():
        # 兼容：未跑 manual 采集器时，直接读 md（旧流程）
        from collectors.manual import ManualCollector

        entries = ManualCollector({}, None)._parse_markdown(manual_path(date_str))
        events.extend(manual_entries_to_events(entries, tags_cfg))

    wecom_file = day_raw / "wecom_schedule.json"
    if wecom_file.is_file():
        wecom_raw = json.loads(wecom_file.read_text(encoding="utf-8"))
        events.extend(wecom_schedule_to_events(wecom_raw, tags_cfg))

    feishu_file = day_raw / "feishu_schedule.json"
    if feishu_file.is_file():
        feishu_raw = json.loads(feishu_file.read_text(encoding="utf-8"))
        events.extend(feishu_schedule_to_events(feishu_raw, tags_cfg))

    return events


def merge_daily(date_str: str, config_path: Path | None = None) -> Path:
    cfg = load_config(config_path)
    tags_cfg = cfg.get("tags") or {}
    timezone = cfg.get("timezone", "Asia/Shanghai")

    ensure_data_dirs(date_str)
    events = dedupe_events(_load_raw_events(date_str, tags_cfg))

    digest = {
        "date": date_str,
        "timezone": timezone,
        "events": events,
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

    for d in dates:
        day = d.isoformat()
        path = digest_path(day)
        if not path.is_file():
            missing_days.append(day)
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
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
        "summary": build_summary(all_events),
    }

    ensure_data_dirs(ref.isoformat())
    out = digest_path(f"week-{dates[0].isoformat()}")
    out.write_text(json.dumps(week_digest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入: {out.relative_to(project_root())}（{len(all_events)} 条事件）")
    if missing_days:
        print(f"缺少日 digest 的日期: {', '.join(missing_days)}")
    return out

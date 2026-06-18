from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def get_timezone(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        from dateutil import tz as dateutil_tz

        fallback = dateutil_tz.gettz(name)
        if fallback is None:
            raise ValueError(f"无法解析时区: {name!r}，请安装 tzdata 或检查 config.timezone")
        return fallback


def resolve_date(value: str, timezone: str = "Asia/Shanghai") -> date:
    """Parse today / yesterday / YYYY-MM-DD into a date in the given timezone."""
    tz = get_timezone(timezone)
    today = datetime.now(tz).date()
    normalized = value.strip().lower()

    if normalized in {"today", "tod"}:
        return today
    if normalized in {"yesterday", "yday"}:
        return today - timedelta(days=1)
    if DATE_PATTERN.match(value.strip()):
        return date.fromisoformat(value.strip())

    raise ValueError(f"无法解析日期: {value!r}，请使用 today / yesterday / YYYY-MM-DD")


def day_bounds(date_str: str, timezone: str = "Asia/Shanghai") -> Tuple[datetime, datetime]:
    """Return [start, end) datetimes for a calendar day in timezone."""
    tz = get_timezone(timezone)
    d = date.fromisoformat(date_str)
    start = datetime.combine(d, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end


def week_date_range(reference: date) -> list[date]:
    """Monday–Sunday week containing reference date."""
    monday = reference - timedelta(days=reference.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def format_week_range(dates: list[date]) -> str:
    if not dates:
        return ""
    start, end = dates[0], dates[-1]
    if start.year == end.year:
        return f"{start.year}-{start.month:02d}-{start.day:02d} ~ {end.month:02d}-{end.day:02d}"
    return f"{start.isoformat()} ~ {end.isoformat()}"

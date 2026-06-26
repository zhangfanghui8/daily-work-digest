"""飞书 CalDAV 连接诊断（勿提交含密码的输出）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collectors.calendar.caldav_client import (
    _discover_feishu_calendar_urls,
    _normalize_server_url,
    fetch_caldav_entries,
)
from utils.config_loader import load_config
from utils.date_utils import resolve_date


def main() -> None:
    config = load_config()
    caldav = (config.get("feishu") or {}).get("caldav") or {}
    base = _normalize_server_url(caldav.get("server") or "https://caldav.feishu.cn")
    user = (caldav.get("username") or "").strip()
    pwd = (caldav.get("password") or "").strip()
    cal_id = (caldav.get("calendar_id") or "").strip() or None
    timezone = config.get("timezone", "Asia/Shanghai")
    date_str = resolve_date("today", timezone).isoformat()

    print(f"server={base}")
    print(f"username={user or '(empty)'}")
    print(f"calendar_id={cal_id or '(auto)'}")
    print(f"date={date_str}")

    if not user or not pwd:
        print("错误: feishu.caldav.username/password 未配置")
        sys.exit(1)

    import httpx

    with httpx.Client(auth=(user, pwd), timeout=30.0, follow_redirects=True) as client:
        urls = _discover_feishu_calendar_urls(client, base, cal_id)
        print(f"discovered calendars: {len(urls)}")
        for u in urls:
            print(f"  {u}")

    entries = fetch_caldav_entries(
        server=base,
        username=user,
        password=pwd,
        date_str=date_str,
        timezone=timezone,
        calendar_id=cal_id,
        provider="feishu",
    )
    print(f"entries for {date_str}: {len(entries)}")
    for e in entries[:5]:
        print(f"  - {e.get('time')} {e.get('title')}")


if __name__ == "__main__":
    main()

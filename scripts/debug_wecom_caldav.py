"""临时诊断企微 CalDAV（勿提交含密码的输出）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collectors.calendar.caldav_client import (
    _discover_wecom_calendar_urls,
    _normalize_server_url,
    fetch_caldav_entries,
)
from utils.config_loader import load_config

PROPFIND_BODY = b"""<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:">
  <D:prop><D:getetag/></D:prop>
</D:propfind>"""


def main() -> None:
    config = load_config()
    caldav = (config.get("wecom") or {}).get("caldav") or {}
    base = _normalize_server_url(caldav.get("server") or "")
    user = (caldav.get("username") or "").strip()
    pwd = (caldav.get("password") or "").strip()
    cal_id = (caldav.get("calendar_id") or "").strip() or None

    print(f"server={base}")
    print(f"username={user}")
    print(f"calendar_id={cal_id or '(auto)'}")

    with httpx.Client(auth=(user, pwd), timeout=30.0, follow_redirects=True) as client:
        urls = _discover_wecom_calendar_urls(client, base, cal_id)
        print(f"discovered calendars: {len(urls)}")
        for u in urls:
            try:
                r = client.request(
                    "PROPFIND",
                    u,
                    content=PROPFIND_BODY,
                    headers={
                        "Depth": "1",
                        "Content-Type": "application/xml; charset=utf-8",
                        "User-Agent": "daily-work-digest/1.0",
                    },
                )
                ics_hrefs = re.findall(r"<[^>]*href[^>]*>([^<]+\.ics)", r.text, re.I)
                print(f"  {u} -> HTTP {r.status_code}, .ics refs: {len(ics_hrefs)}")
                if ics_hrefs[:2]:
                    print(f"    sample: {ics_hrefs[:2]}")
            except httpx.HTTPError as exc:
                print(f"  {u} -> ERROR {exc}")

        entries = fetch_caldav_entries(
            server=base,
            username=user,
            password=pwd,
            date_str="2026-06-18",
            timezone=config.get("timezone", "Asia/Shanghai"),
            calendar_id=cal_id,
            provider="wecom",
        )
        print(f"entries for today: {len(entries)}")
        for e in entries[:5]:
            print(f"  - {e.get('time')} {e.get('title')}")

        if not entries and urls:
            print("\n--- sample events (first 10 .ics) ---")
            from icalendar import Calendar

            from collectors.calendar.caldav_client import _get_text, _resolve_href

            r = client.request(
                "PROPFIND",
                urls[0],
                content=PROPFIND_BODY,
                headers={
                    "Depth": "1",
                    "Content-Type": "application/xml; charset=utf-8",
                    "User-Agent": "daily-work-digest/1.0",
                },
            )
            hrefs = re.findall(r"<[^>]*href[^>]*>([^<]+\.ics)", r.text, re.I)
            for href in hrefs[:10]:
                url = _resolve_href(urls[0], href)
                try:
                    text = _get_text(client, url)
                    cal_obj = Calendar.from_ical(text)
                except Exception as exc:
                    print(f"  skip {href}: {exc}")
                    continue
                for comp in cal_obj.walk():
                    if comp.name != "VEVENT":
                        continue
                    print(f"  {comp.get('summary')} | start={comp.get('dtstart').dt}")
                    break


if __name__ == "__main__":
    main()

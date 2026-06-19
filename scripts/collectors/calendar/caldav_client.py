from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx
from icalendar import Calendar
from utils.date_utils import day_bounds

CALENDAR_ID_RE = re.compile(r"/calendar/(\d+)/")


def _safe_id(uid: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "", uid)[:48]
    if cleaned:
        return cleaned
    return hashlib.md5(uid.encode("utf-8")).hexdigest()[:16]


def _normalize_server_url(server: str) -> str:
    url = server.strip().rstrip("/")
    if not url.startswith("http"):
        url = f"https://{url}"
    return url


def _utc_range(day_start: datetime, day_end: datetime) -> tuple[str, str]:
    start_utc = day_start.astimezone(ZoneInfo("UTC"))
    end_utc = (day_end - timedelta(seconds=1)).astimezone(ZoneInfo("UTC"))
    return (
        start_utc.strftime("%Y%m%dT%H%M%SZ"),
        end_utc.strftime("%Y%m%dT%H%M%SZ"),
    )


def _to_local_dt(value: date | datetime, tz: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=tz)
        return value.astimezone(tz)
    return datetime.combine(value, datetime.min.time(), tzinfo=tz)


def _event_overlaps_day(start: datetime, end: datetime, day_start: datetime, day_end: datetime) -> bool:
    if end <= start:
        end = start + timedelta(hours=1)
    return start < day_end and end > day_start


def _parse_vevent(vevent: Any, tz: ZoneInfo, day_start: datetime, day_end: datetime) -> dict[str, Any] | None:
    status = str(vevent.get("status") or "").upper()
    if status == "CANCELLED":
        return None

    uid = str(vevent.get("uid") or "")
    summary = str(vevent.get("summary") or "").strip() or "无标题日程"
    location = str(vevent.get("location") or "").strip()
    description = str(vevent.get("description") or "").strip()

    dtstart_prop = vevent.get("dtstart")
    if dtstart_prop is None:
        return None

    start = _to_local_dt(dtstart_prop.dt, tz)
    dtend_prop = vevent.get("dtend")
    if dtend_prop is not None:
        end = _to_local_dt(dtend_prop.dt, tz)
    else:
        end = start + timedelta(hours=1)

    if not _event_overlaps_day(start, end, day_start, day_end):
        return None

    all_day = not isinstance(dtstart_prop.dt, datetime)
    display_start = day_start if all_day else start
    if all_day and not summary.startswith("[全天]"):
        summary = f"[全天] {summary}"

    detail_parts = []
    if location:
        detail_parts.append(f"地点: {location}")
    duration_min = max(int((end - start).total_seconds() // 60), 0)
    if duration_min > 0 and not all_day:
        detail_parts.append(f"时长: {duration_min} 分钟")

    return {
        "id": f"cal-{_safe_id(uid)}",
        "uid": uid,
        "title": summary,
        "time": display_start.strftime("%H:%M:%S"),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "location": location,
        "description": description[:200] if description else "",
        "all_day": all_day,
        "detail": " | ".join(detail_parts),
    }


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _find_text(parent: Any, name: str) -> str | None:
    for child in parent.iter():
        if _local_name(child.tag) == name and child.text:
            return child.text.strip()
    return None


def _extract_calendar_ids_from_text(text: str) -> list[str]:
    return list(dict.fromkeys(CALENDAR_ID_RE.findall(text)))


def _caldav_headers(depth: str) -> dict[str, str]:
    return {
        "Depth": depth,
        "Content-Type": "application/xml; charset=utf-8",
        "User-Agent": "daily-work-digest/1.0",
    }


def _propfind(client: httpx.Client, url: str, body: str, depth: str = "0") -> Any:
    response = client.request(
        "PROPFIND",
        url,
        content=body.encode("utf-8"),
        headers=_caldav_headers(depth),
    )
    response.raise_for_status()
    import xml.etree.ElementTree as ET

    return ET.fromstring(response.content)


def _report(client: httpx.Client, url: str, body: str, depth: str = "1") -> Any:
    response = client.request(
        "REPORT",
        url,
        content=body.encode("utf-8"),
        headers=_caldav_headers(depth),
    )
    response.raise_for_status()
    import xml.etree.ElementTree as ET

    return ET.fromstring(response.content)


def _get_text(client: httpx.Client, url: str) -> str:
    response = client.get(url, headers={"User-Agent": "daily-work-digest/1.0"})
    response.raise_for_status()
    return response.text


def _calendar_query_body(start_utc: str, end_utc: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="{start_utc}" end="{end_utc}"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""


def _resolve_href(base_url: str, href: str) -> str:
    href = href.strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{href}"
    return urljoin(base_url if base_url.endswith("/") else base_url + "/", href)


def _list_hrefs(xml_root: Any) -> list[str]:
    hrefs: list[str] = []
    for elem in xml_root.iter():
        if _local_name(elem.tag) == "href" and elem.text:
            hrefs.append(elem.text.strip())
    return hrefs


def _extract_calendar_data(xml_root: Any) -> list[str]:
    payloads: list[str] = []
    for elem in xml_root.iter():
        if _local_name(elem.tag) == "calendar-data" and elem.text:
            payloads.append(elem.text.strip())
    return payloads


def _parse_ics_entries(
    ics_texts: list[str],
    tz: ZoneInfo,
    day_start: datetime,
    day_end: datetime,
    seen_uids: set[str],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for ics_text in ics_texts:
        try:
            cal = Calendar.from_ical(ics_text)
        except Exception:
            continue
        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            parsed = _parse_vevent(component, tz, day_start, day_end)
            if parsed is None:
                continue
            uid = parsed.get("uid") or parsed["id"]
            if uid in seen_uids:
                continue
            seen_uids.add(uid)
            entries.append(parsed)
    return entries


def _resolve_wecom_calendar_url(base_url: str, calendar_id: str | None) -> str:
    parsed = urlparse(base_url)
    host_base = f"{parsed.scheme}://{parsed.netloc}"
    cal_id = (calendar_id or "").strip()
    if cal_id:
        return f"{host_base}/calendar/{cal_id}/"
    return f"{host_base}/calendar/"


def _discover_wecom_calendar_urls(
    client: httpx.Client,
    base_url: str,
    calendar_id: str | None,
) -> list[str]:
    if calendar_id:
        return [_resolve_wecom_calendar_url(base_url, calendar_id)]

    candidates: list[str] = []
    host_base = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"

    # 企微常见结构：/calendar/{corp_numeric_id}/
    probe_urls = [
        f"{host_base}/calendar/",
        base_url,
    ]

    list_body = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:resourcetype/>
    <D:displayname/>
  </D:prop>
</D:propfind>"""

    for probe in probe_urls:
        try:
            xml_root = _propfind(client, probe, list_body, depth="1")
        except httpx.HTTPError:
            continue

        for href in _list_hrefs(xml_root):
            for cal_id in _extract_calendar_ids_from_text(href):
                candidates.append(f"{host_base}/calendar/{cal_id}/")

    # 去重
    seen: set[str] = set()
    unique: list[str] = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _fetch_via_calendar_query(
    client: httpx.Client,
    calendar_url: str,
    query_body: str,
) -> list[str]:
    xml_root = _report(client, calendar_url, query_body, depth="1")
    return _extract_calendar_data(xml_root)


def _fetch_via_ics_list(
    client: httpx.Client,
    calendar_url: str,
    tz: ZoneInfo,
    day_start: datetime,
    day_end: datetime,
) -> list[str]:
    """企微兼容：PROPFIND 列出 .ics 再 GET（避免部分 REPORT 403）。"""
    list_body = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:getetag/>
    <D:getcontenttype/>
  </D:prop>
</D:propfind>"""

    xml_root = _propfind(client, calendar_url, list_body, depth="1")
    ics_texts: list[str] = []

    for href in _list_hrefs(xml_root):
        if not href.lower().endswith(".ics"):
            continue
        ics_url = _resolve_href(calendar_url, href)
        try:
            ics_texts.append(_get_text(client, ics_url))
        except httpx.HTTPError:
            continue

    return ics_texts


def _fetch_via_multiget(
    client: httpx.Client,
    calendar_url: str,
) -> list[str]:
    """飞书兼容：PROPFIND 列出 .ics，再 calendar-multiget 获取 calendar-data。

    飞书 CalDAV 不支持 calendar-query REPORT（返回空结果），也不允许 GET
    单个 .ics 文件（403），但支持 calendar-multiget 批量获取已列出的资源。
    """
    list_body = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:getetag/>
    <D:getcontenttype/>
  </D:prop>
</D:propfind>"""

    xml_root = _propfind(client, calendar_url, list_body, depth="1")
    hrefs = [h for h in _list_hrefs(xml_root) if h.lower().endswith(".ics")]

    if not hrefs:
        return []

    href_xml = "\n".join(f"    <D:href>{h}</D:href>" for h in hrefs)
    multiget_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<C:calendar-multiget xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
{href_xml}
</C:calendar-multiget>"""

    xml_root2 = _report(client, calendar_url, multiget_body, depth="1")
    return _extract_calendar_data(xml_root2)


def _calendar_not_found_message(provider: str) -> str:
    hints = {
        "wecom": (
            "未找到企微 CalDAV 日历路径。"
            "请在 config.yaml 的 wecom.caldav.calendar_id 填写企业日历 ID（数字），"
            "或确认用户名/密码来自手机「同步至其他日历」而非登录密码。"
        ),
        "feishu": (
            "未找到飞书 CalDAV 日历路径。"
            "请在飞书桌面端「设置 → 日历 → CalDAV 同步」重新生成专用账号密码；"
            "服务器通常为 https://caldav.feishu.cn；"
            "若仍失败可配置 feishu.caldav.calendar_id（日历 URL 或路径）。"
        ),
    }
    return hints.get(provider, "未找到 CalDAV 日历路径，请检查 server、username、password 配置。")


def _discover_feishu_calendar_urls(
    client: httpx.Client,
    base_url: str,
    calendar_id: str | None,
) -> list[str]:
    cal_id = (calendar_id or "").strip()
    if cal_id.startswith("http://") or cal_id.startswith("https://"):
        url = cal_id.rstrip("/")
        return [url if url.endswith("/") else url + "/"]

    urls = _discover_generic_calendar_urls(client, base_url)
    if urls:
        return urls

    if cal_id:
        host = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
        path = cal_id if cal_id.startswith("/") else f"/{cal_id}"
        url = f"{host}{path}".rstrip("/") + "/"
        return [url]

    # 飞书部分环境需从 /dav/ 探测
    host = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"
    for probe in (f"{host}/dav/", base_url):
        found = _discover_generic_calendar_urls(client, probe.rstrip("/"))
        if found:
            return found

    return []


def fetch_caldav_entries(
    server: str,
    username: str,
    password: str,
    date_str: str,
    timezone: str = "Asia/Shanghai",
    calendar_id: str | None = None,
    provider: str = "wecom",
) -> list[dict[str, Any]]:
    """通过 CalDAV 拉取与指定日期重叠的日程条目。"""
    if not server or not username or not password:
        raise ValueError("CalDAV 配置不完整，需要 server、username、password")

    tz = ZoneInfo(timezone)
    day_start, day_end = day_bounds(date_str, timezone)
    start_utc, end_utc = _utc_range(day_start, day_end)
    base_url = _normalize_server_url(server)
    query_body = _calendar_query_body(start_utc, end_utc)

    entries: list[dict[str, Any]] = []
    seen_uids: set[str] = set()
    errors: list[str] = []

    with httpx.Client(auth=(username, password), timeout=30.0, follow_redirects=True) as client:
        if provider == "wecom":
            calendar_urls = _discover_wecom_calendar_urls(client, base_url, calendar_id)
        elif provider == "feishu":
            calendar_urls = _discover_feishu_calendar_urls(client, base_url, calendar_id)
        else:
            calendar_urls = _discover_generic_calendar_urls(client, base_url)

        if not calendar_urls:
            raise RuntimeError(_calendar_not_found_message(provider))

        for calendar_url in calendar_urls:
            ics_texts: list[str] = []
            try:
                ics_texts = _fetch_via_calendar_query(client, calendar_url, query_body)
            except httpx.HTTPError as exc:
                errors.append(f"REPORT {calendar_url}: {exc}")

            if not ics_texts and provider == "feishu":
                try:
                    ics_texts = _fetch_via_multiget(client, calendar_url)
                except httpx.HTTPError as exc:
                    errors.append(f"multiget {calendar_url}: {exc}")

            if not ics_texts:
                try:
                    ics_texts = _fetch_via_ics_list(client, calendar_url, tz, day_start, day_end)
                except httpx.HTTPError as exc:
                    errors.append(f"PROPFIND {calendar_url}: {exc}")
                    continue

            entries.extend(_parse_ics_entries(ics_texts, tz, day_start, day_end, seen_uids))

    if not entries and errors:
        detail = errors[0]
        if "403" in detail:
            if provider == "feishu":
                raise RuntimeError(
                    f"{detail}。"
                    "常见原因：1) CalDAV 专用密码过期，请在飞书重新生成；"
                    "2) 用户名/密码须来自「CalDAV 同步」而非飞书登录密码；"
                    "3) 可配置 feishu.caldav.calendar_id。"
                )
            raise RuntimeError(
                f"{detail}。"
                "常见原因：1) 同步密码过期，请手机重新获取；"
                "2) 需配置 wecom.caldav.calendar_id；"
                "3) 用户名须与手机「同步至其他日历」完全一致。"
            )
        raise RuntimeError(detail)

    entries.sort(key=lambda e: str(e.get("time") or ""))
    return entries


def _discover_generic_calendar_urls(client: httpx.Client, base_url: str) -> list[str]:
    propfind_root = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:current-user-principal/>
    <C:calendar-home-set/>
  </D:prop>
</D:propfind>"""

    try:
        root_xml = _propfind(client, base_url, propfind_root, depth="0")
    except httpx.HTTPError:
        return []

    calendar_home = None
    for elem in root_xml.iter():
        if _local_name(elem.tag) == "calendar-home-set":
            calendar_home = _find_text(elem, "href")
            break

    if not calendar_home:
        return []

    home_url = _resolve_href(base_url, calendar_home)
    list_body = """<?xml version="1.0" encoding="utf-8"?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:resourcetype/>
  </D:prop>
</D:propfind>"""
    try:
        xml_root = _propfind(client, home_url, list_body, depth="1")
    except httpx.HTTPError:
        return [home_url]

    calendars: list[str] = []
    for href in _list_hrefs(xml_root):
        full_url = _resolve_href(home_url, href)
        if full_url.rstrip("/") != home_url.rstrip("/"):
            calendars.append(full_url if full_url.endswith("/") else full_url + "/")
    return calendars or [home_url]

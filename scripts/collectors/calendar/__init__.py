"""CalDAV 日历采集公共逻辑（企微 / 钉钉 / 飞书可复用）。"""

from .caldav_client import fetch_caldav_entries

__all__ = ["fetch_caldav_entries"]

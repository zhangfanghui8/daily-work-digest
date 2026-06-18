from __future__ import annotations

from typing import Any, ClassVar

from collectors.calendar.caldav_client import fetch_caldav_entries

from .base import BaseCollector


class WeComScheduleCollector(BaseCollector):
    """企业微信日程：通过 CalDAV 直连 caldav.wecom.work 读取，不同步到第三方日历。"""

    source: ClassVar[str] = "wecom"
    output_filename: ClassVar[str] = "wecom_schedule.json"

    @classmethod
    def source_name(cls) -> str:
        return cls.source

    @classmethod
    def is_enabled(cls, config: dict[str, Any]) -> bool:
        wecom = config.get("wecom") or {}
        if not wecom.get("enabled", False):
            return False
        caldav = wecom.get("caldav") or {}
        return bool((caldav.get("username") or "").strip() and (caldav.get("password") or "").strip())

    def collect(self, date_str: str) -> dict[str, Any]:
        wecom = self.config.get("wecom") or {}
        caldav = wecom.get("caldav") or {}
        server = (caldav.get("server") or "https://caldav.wecom.work").strip()
        username = (caldav.get("username") or "").strip()
        password = (caldav.get("password") or "").strip()

        try:
            entries = fetch_caldav_entries(
                server=server,
                username=username,
                password=password,
                date_str=date_str,
                timezone=self.timezone,
                calendar_id=(caldav.get("calendar_id") or "").strip() or None,
                provider="wecom",
            )
        except Exception as exc:
            raise RuntimeError(
                f"企微 CalDAV 采集失败: {exc}。"
                "请检查 wecom.caldav 的用户名/密码（须来自手机「同步至其他日历」，非登录密码）；"
                "若仍 403，可配置 calendar_id（见 docs/企微日程采集-用户指南.md）。"
            ) from exc

        print(f"  └─ {len(entries)} 条日程")
        return {
            "date": date_str,
            "timezone": self.timezone,
            "source": self.source,
            "provider": "caldav",
            "server": server,
            "entries": entries,
        }

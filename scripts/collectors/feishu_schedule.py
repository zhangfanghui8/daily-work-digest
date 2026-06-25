from __future__ import annotations

from typing import Any, ClassVar

from collectors.calendar.caldav_client import fetch_caldav_entries

from .base import BaseCollector


class FeishuScheduleCollector(BaseCollector):
    """飞书日程：通过 CalDAV 直连 caldav.feishu.cn 读取。

    需要在飞书日历设置中生成 CalDAV 账号密码，填入 config.yaml。
    """

    source: ClassVar[str] = "feishu"
    output_filename: ClassVar[str] = "feishu_schedule.json"

    @classmethod
    def source_name(cls) -> str:
        return cls.source

    @classmethod
    def is_enabled(cls, config: dict[str, Any]) -> bool:
        feishu = config.get("feishu") or {}
        if not feishu.get("enabled", False):
            return False
        caldav = feishu.get("caldav") or {}
        return bool((caldav.get("username") or "").strip() and (caldav.get("password") or "").strip())

    def collect(self, date_str: str) -> dict[str, Any]:
        feishu = self.config.get("feishu") or {}
        caldav = feishu.get("caldav") or {}
        server = (caldav.get("server") or "https://caldav.feishu.cn").strip()
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
                provider="feishu",
            )
        except Exception as exc:
            raise RuntimeError(
                f"飞书 CalDAV 采集失败: {exc}。"
                "请检查 feishu.caldav 配置（见 docs/飞书日程采集-用户指南.md）："
                "1) 飞书桌面端「设置 → 日历 → CalDAV 同步」生成专用账号密码"
                "2) 服务器通常为 https://caldav.feishu.cn"
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

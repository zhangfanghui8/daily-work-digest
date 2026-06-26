from __future__ import annotations

from typing import Any, ClassVar

from collectors.calendar.caldav_client import fetch_caldav_entries

from .base import BaseCollector


class DingTalkScheduleCollector(BaseCollector):
    """钉钉日程：通过 CalDAV 直连 caldav.mxhichina.com 读取。

    需要在钉钉客户端「日历 → 设置 → CalDAV 同步」生成专用账号密码，填入 config.yaml。
    """

    source: ClassVar[str] = "dingtalk"
    output_filename: ClassVar[str] = "dingtalk_schedule.json"

    @classmethod
    def source_name(cls) -> str:
        return cls.source

    @classmethod
    def is_enabled(cls, config: dict[str, Any]) -> bool:
        dingtalk = config.get("dingtalk") or {}
        if not dingtalk.get("enabled", False):
            return False
        caldav = dingtalk.get("caldav") or {}
        return bool((caldav.get("username") or "").strip() and (caldav.get("password") or "").strip())

    def collect(self, date_str: str) -> dict[str, Any]:
        dingtalk = self.config.get("dingtalk") or {}
        caldav = dingtalk.get("caldav") or {}
        server = (caldav.get("server") or "https://caldav.mxhichina.com").strip()
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
                provider="dingtalk",
            )
        except Exception as exc:
            raise RuntimeError(
                f"钉钉 CalDAV 采集失败: {exc}。"
                "请检查 dingtalk.caldav 配置（PC端钉钉「日历 → 设置 → CalDAV同步」生成专用账号密码）："
                "1) 服务器通常为 https://caldav.mxhichina.com"
                "2) 用户名/密码须来自钉钉 CalDAV 同步，非钉钉登录密码"
                "3) 密码为一次性生成，若丢失需重新生成"
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

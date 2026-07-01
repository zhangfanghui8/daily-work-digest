from __future__ import annotations

from typing import Any, ClassVar

from collectors.pms.zentao_client import ZenTaoApiError, ensure_token, fetch_entries_for_day

from .base import BaseCollector


class ZenTaoCollector(BaseCollector):
    """禅道：拉取指定日期 Bug / 需求 / 任务变更（L1 元数据）。

    用户只需配置 base_url；登录凭证通过 zentao_auth.py --login 写入本地缓存。
    见 docs/禅道采集-用户指南.md。
    """

    source: ClassVar[str] = "zentao"
    output_filename: ClassVar[str] = "zentao.json"

    @classmethod
    def source_name(cls) -> str:
        return cls.source

    @classmethod
    def is_enabled(cls, config: dict[str, Any]) -> bool:
        zentao = config.get("zentao") or {}
        if not zentao.get("enabled", False):
            return False
        return bool((zentao.get("base_url") or "").strip())

    def collect(self, date_str: str) -> dict[str, Any]:
        zentao = self.config.get("zentao") or {}
        try:
            token, account, base_url = ensure_token(zentao)
            result = fetch_entries_for_day(
                zentao,
                date_str=date_str,
                token=token,
                account=account,
                base_url=base_url,
            )
        except ZenTaoApiError as exc:
            raise RuntimeError(f"禅道采集失败: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"禅道采集失败: {exc}。见 docs/禅道采集-用户指南.md") from exc

        entries = result.get("entries") or []
        stats = result.get("stats") or {}
        bugs = stats.get("bugs", 0)
        stories = stats.get("stories", 0)
        tasks = stats.get("tasks", 0)
        scope = "自动发现" if result.get("auto_discover") else "白名单"
        print(
            f"  └─ {len(entries)} 条变更（Bug {bugs} / 需求 {stories} / 任务 {tasks}·{scope}）"
        )
        return {
            "date": date_str,
            "timezone": self.timezone,
            "source": self.source,
            "provider": "rest_api_v2",
            "base_url": base_url,
            "account": account,
            "only_my_activity": result.get("only_my_activity", True),
            "stats": stats,
            "entries": entries,
        }

from __future__ import annotations

from typing import Any, ClassVar

from collectors.pms.jira_client import JiraApiError, fetch_entries_for_day

from .base import BaseCollector


class JiraCollector(BaseCollector):
    """私有化 Jira Server/Data Center：JQL 拉取当日 Issue 变更（L1）。

    用户配置 base_url + PAT（Personal Access Token）；见 docs/Jira采集-用户指南.md。
    """

    source: ClassVar[str] = "jira"
    output_filename: ClassVar[str] = "jira.json"

    @classmethod
    def source_name(cls) -> str:
        return cls.source

    @classmethod
    def is_enabled(cls, config: dict[str, Any]) -> bool:
        jira = config.get("jira") or {}
        if not jira.get("enabled", False):
            return False
        return bool((jira.get("base_url") or "").strip())

    def collect(self, date_str: str) -> dict[str, Any]:
        jira = self.config.get("jira") or {}
        try:
            result = fetch_entries_for_day(jira, date_str=date_str)
        except JiraApiError as exc:
            raise RuntimeError(f"Jira 采集失败: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Jira 采集失败: {exc}。见 docs/Jira采集-用户指南.md") from exc

        entries = result.get("entries") or []
        stats = result.get("stats") or {}
        print(
            f"  └─ {len(entries)} 条 Issue（Bug {stats.get('bug', 0)} / "
            f"Story {stats.get('story', 0)} / Task {stats.get('task', 0)}·server）"
        )
        return {
            "date": date_str,
            "timezone": self.timezone,
            "source": self.source,
            "provider": "rest_api_v2_server",
            "base_url": (jira.get("base_url") or "").strip(),
            "deployment": "server",
            "jql": result.get("jql") or "",
            "username": result.get("username") or "",
            "only_my_activity": result.get("only_my_activity", True),
            "stats": stats,
            "entries": entries,
        }

from __future__ import annotations

from typing import Any, ClassVar

from collectors.docs.feishu_client import FeishuOpenApiError, fetch_doc_entries_for_day

from .base import BaseCollector


class FeishuDocsCollector(BaseCollector):
    """飞书文档：通过搜索 API 拉取指定日期「我编辑过的」云文档/Wiki 元数据（L1）。

    需 user_access_token 或 refresh_token（OAuth 用户授权），见 docs/飞书文档采集-用户指南.md。
    """

    source: ClassVar[str] = "feishu_docs"
    output_filename: ClassVar[str] = "feishu_docs.json"

    @classmethod
    def source_name(cls) -> str:
        return cls.source

    @classmethod
    def is_enabled(cls, config: dict[str, Any]) -> bool:
        feishu = config.get("feishu") or {}
        docs = feishu.get("docs") or {}
        if not docs.get("enabled", False):
            return False
        if (docs.get("user_access_token") or "").strip():
            return True
        if (docs.get("refresh_token") or "").strip():
            return True
        from collectors.docs.feishu_client import resolve_token_cache_path

        return resolve_token_cache_path(docs).is_file()

    def collect(self, date_str: str) -> dict[str, Any]:
        feishu = self.config.get("feishu") or {}
        docs = feishu.get("docs") or {}

        try:
            entries = fetch_doc_entries_for_day(
                docs,
                feishu,
                date_str=date_str,
                timezone=self.timezone,
            )
        except FeishuOpenApiError as exc:
            raise RuntimeError(
                f"飞书文档采集失败: {exc}。"
                "请检查 feishu.docs 配置（见 docs/飞书文档采集-用户指南.md）："
                "1) 申请 search:docs:read 权限"
                "2) 运行 python scripts/feishu_oauth.py --login（Agent 可代劳，用户只需浏览器点同意）"
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"飞书文档采集失败: {exc}。见 docs/飞书文档采集-用户指南.md"
            ) from exc

        print(f"  └─ {len(entries)} 篇编辑过的文档")
        return {
            "date": date_str,
            "timezone": self.timezone,
            "source": self.source,
            "provider": "search_api",
            "mode": "my_edit_time",
            "include_types": list(docs.get("include_types") or []),
            "entries": entries,
        }

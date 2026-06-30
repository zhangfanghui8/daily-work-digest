from __future__ import annotations

from typing import Any, ClassVar

from collectors.docs.yuque_client import (
    YuqueOpenApiError,
    fetch_doc_entries_for_day,
    resolve_auth,
    resolve_auth_mode,
)

from .base import BaseCollector


class YuqueDocsCollector(BaseCollector):
    """语雀文档：拉取指定日期编辑过的文档元数据（L1）。

    支持 Token 或 Cookie；repos 可留空，自动扫描账号下知识库。
    """

    source: ClassVar[str] = "yuque_docs"
    output_filename: ClassVar[str] = "yuque_docs.json"

    @classmethod
    def source_name(cls) -> str:
        return cls.source

    @classmethod
    def is_enabled(cls, config: dict[str, Any]) -> bool:
        yuque = config.get("yuque") or {}
        docs = yuque.get("docs") or {}
        if not docs.get("enabled", False):
            return False
        try:
            resolve_auth(docs)
            return True
        except YuqueOpenApiError:
            return False

    def collect(self, date_str: str) -> dict[str, Any]:
        yuque = self.config.get("yuque") or {}
        docs = yuque.get("docs") or {}
        auth_mode = resolve_auth_mode(docs)

        try:
            result = fetch_doc_entries_for_day(
                docs,
                date_str=date_str,
                timezone=self.timezone,
            )
        except YuqueOpenApiError as exc:
            if auth_mode == "cookie":
                hint = (
                    "请检查 yuque.docs（见 docs/语雀文档采集-用户指南.md）："
                    "1) auth_mode 设为 cookie"
                    "2) 在 cookie 中填写浏览器复制的 Cookie"
                )
            else:
                hint = (
                    "请检查 yuque.docs 配置（见 docs/语雀文档采集-用户指南.md）："
                    "1) 在语雀设置页创建 Token，或改用 auth_mode: cookie"
                    "2) 在 token 中填写 Token"
                )
            raise RuntimeError(f"语雀文档采集失败: {exc}。{hint}") from exc
        except Exception as exc:
            raise RuntimeError(
                f"语雀文档采集失败: {exc}。见 docs/语雀文档采集-用户指南.md"
            ) from exc

        entries = result.get("entries") or []
        namespaces = result.get("repos") or []
        repos_auto = bool(result.get("repos_auto"))
        scope = "自动发现" if repos_auto else "白名单"

        print(f"  └─ {len(entries)} 篇编辑过的文档（{len(namespaces)} 个知识库·{scope}）")
        return {
            "date": date_str,
            "timezone": self.timezone,
            "source": self.source,
            "provider": "open_api",
            "auth_mode": auth_mode,
            "repos": namespaces,
            "repos_auto": repos_auto,
            "filters": {
                "only_my_edits": bool(docs.get("only_my_edits", True)),
                "use_content_updated_at": bool(docs.get("use_content_updated_at", True)),
                "also_use_updated_at": bool(docs.get("also_use_updated_at", True)),
            },
            "entries": entries,
        }

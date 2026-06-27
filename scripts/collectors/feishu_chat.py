from __future__ import annotations

from typing import Any, ClassVar

from collectors.chat.feishu_client import FeishuOpenApiError, fetch_chat_entries_for_day

from .base import BaseCollector


class FeishuChatCollector(BaseCollector):
    """飞书 IM：通过开放平台 API 拉取指定群聊/单聊的历史消息。

    需在飞书开发者后台创建企业自建应用，申请 IM 相关权限，并将机器人加入目标群。
    配置见 docs/飞书IM采集-用户指南.md。
    """

    source: ClassVar[str] = "feishu_chat"
    output_filename: ClassVar[str] = "feishu_chat.json"

    @classmethod
    def source_name(cls) -> str:
        return cls.source

    @classmethod
    def is_enabled(cls, config: dict[str, Any]) -> bool:
        feishu = config.get("feishu") or {}
        chat = feishu.get("chat") or {}
        if not chat.get("enabled", False):
            return False
        app_id = (chat.get("app_id") or "").strip()
        app_secret = (chat.get("app_secret") or "").strip()
        if not app_id or not app_secret:
            return False
        chat_ids = [c for c in (chat.get("chat_ids") or []) if str(c).strip()]
        p2p_ids = [c for c in (chat.get("p2p_chat_ids") or []) if str(c).strip()]
        return bool(chat_ids or p2p_ids)

    def collect(self, date_str: str) -> dict[str, Any]:
        feishu = self.config.get("feishu") or {}
        chat = feishu.get("chat") or {}
        app_id = (chat.get("app_id") or "").strip()
        app_secret = (chat.get("app_secret") or "").strip()
        base_url = (chat.get("base_url") or "https://open.feishu.cn").strip()
        chat_ids = [str(c).strip() for c in (chat.get("chat_ids") or []) if str(c).strip()]
        p2p_ids = [str(c).strip() for c in (chat.get("p2p_chat_ids") or []) if str(c).strip()]
        all_chat_ids = chat_ids + p2p_ids

        only_my_messages = bool(chat.get("only_my_messages", False))
        only_mention_me = bool(chat.get("only_mention_me", False))
        my_open_id = (chat.get("my_open_id") or "").strip()
        if (only_my_messages or only_mention_me) and not my_open_id:
            raise RuntimeError(
                "飞书 IM 采集：已开启 only_my_messages / only_mention_me，但未配置 feishu.chat.my_open_id。"
                "见 docs/飞书IM采集-用户指南.md"
            )

        try:
            entries = fetch_chat_entries_for_day(
                app_id=app_id,
                app_secret=app_secret,
                chat_ids=all_chat_ids,
                date_str=date_str,
                timezone=self.timezone,
                base_url=base_url,
                only_my_messages=only_my_messages,
                only_mention_me=only_mention_me,
                my_open_id=my_open_id,
                keywords=list(chat.get("keywords") or []),
                exclude_keywords=list(chat.get("exclude_keywords") or []),
                page_size=int(chat.get("page_size") or 50),
                max_pages=int(chat.get("max_pages") or 20),
            )
        except FeishuOpenApiError as exc:
            raise RuntimeError(
                f"飞书 IM 采集失败: {exc}。"
                "请检查 feishu.chat 配置与开放平台权限（见 docs/飞书IM采集-用户指南.md）："
                "1) 企业自建应用 app_id / app_secret"
                "2) 开启 im:message:readonly 与 im:message.group_msg（群聊）"
                "3) 启用机器人能力并将机器人加入目标群"
                "4) chat_ids 填写正确的 open_chat_id"
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"飞书 IM 采集失败: {exc}。见 docs/飞书IM采集-用户指南.md"
            ) from exc

        print(f"  └─ {len(entries)} 条 IM 消息（{len(all_chat_ids)} 个会话）")
        return {
            "date": date_str,
            "timezone": self.timezone,
            "source": self.source,
            "provider": "open_api",
            "base_url": base_url,
            "chat_ids": all_chat_ids,
            "filters": {
                "only_my_messages": only_my_messages,
                "only_mention_me": only_mention_me,
                "keywords": list(chat.get("keywords") or []),
                "exclude_keywords": list(chat.get("exclude_keywords") or []),
            },
            "entries": entries,
        }

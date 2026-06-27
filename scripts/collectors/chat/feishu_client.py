from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://open.feishu.cn"


class FeishuOpenApiError(RuntimeError):
    """飞书 Open API 调用失败。"""


def _api_base(base_url: str) -> str:
    return base_url.rstrip("/")


def get_tenant_access_token(
    app_id: str,
    app_secret: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    client: httpx.Client | None = None,
) -> str:
    """获取 tenant_access_token（企业自建应用）。"""
    url = f"{_api_base(base_url)}/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": app_id, "app_secret": app_secret}
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        resp = http.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise FeishuOpenApiError(
                f"获取 tenant_access_token 失败: code={data.get('code')} msg={data.get('msg')}"
            )
        token = data.get("tenant_access_token") or ""
        if not token:
            raise FeishuOpenApiError("获取 tenant_access_token 失败: 响应缺少 token")
        return token
    finally:
        if own_client:
            http.close()


def _parse_body_content(raw_content: Any) -> dict[str, Any]:
    if isinstance(raw_content, dict):
        return raw_content
    if isinstance(raw_content, str) and raw_content.strip():
        try:
            parsed = json.loads(raw_content)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {"text": raw_content}
    return {}


def _extract_post_text(content: dict[str, Any]) -> str:
    post = content.get("post") or content.get("zh_cn") or content
    if not isinstance(post, dict):
        return ""
    parts: list[str] = []
    title = post.get("title")
    if isinstance(title, str) and title.strip():
        parts.append(title.strip())
    body = post.get("content")
    if isinstance(body, list):
        for row in body:
            if not isinstance(row, list):
                continue
            for cell in row:
                if not isinstance(cell, dict):
                    continue
                tag = cell.get("tag")
                if tag == "text":
                    text = cell.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                elif tag == "a":
                    text = cell.get("text") or cell.get("href") or ""
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
    return "\n".join(parts)


def extract_message_text(msg_type: str, body: dict[str, Any] | None) -> str:
    """从飞书消息 body 提取可读文本。"""
    body = body or {}
    content = _parse_body_content(body.get("content"))

    if msg_type == "text":
        text = content.get("text")
        return text.strip() if isinstance(text, str) else ""

    if msg_type == "post":
        return _extract_post_text(content)

    if msg_type == "image":
        return "[图片]"

    if msg_type in {"file", "folder"}:
        name = content.get("file_name") or content.get("name") or ""
        return f"[文件] {name}".strip()

    if msg_type == "audio":
        return "[语音]"

    if msg_type == "media":
        return "[视频]"

    if msg_type == "sticker":
        return "[表情]"

    if msg_type == "interactive":
        return "[卡片消息]"

    if msg_type == "share_chat":
        return "[分享群聊]"

    if msg_type == "share_user":
        return "[分享名片]"

    if msg_type == "system":
        return "[系统消息]"

    if content:
        return json.dumps(content, ensure_ascii=False)

    return f"[{msg_type or 'unknown'}]"


def _message_mentions_me(message: dict[str, Any], my_open_id: str) -> bool:
    if not my_open_id:
        return False
    for mention in message.get("mentions") or []:
        if not isinstance(mention, dict):
            continue
        mention_id = mention.get("id") or mention.get("open_id") or ""
        if mention_id == my_open_id:
            return True
    body = message.get("body") or {}
    content = _parse_body_content(body.get("content"))
    text = content.get("text")
    if isinstance(text, str) and my_open_id and f"@{my_open_id}" in text:
        return True
    return False


def _matches_keywords(text: str, keywords: list[str], exclude_keywords: list[str]) -> bool:
    lowered = text.lower()
    if exclude_keywords and any(k.lower() in lowered for k in exclude_keywords if k):
        return False
    if not keywords:
        return True
    return any(k.lower() in lowered for k in keywords if k)


def _create_time_to_hms(create_time: str | int | float, timezone: str) -> str:
    try:
        ts = int(str(create_time))
    except (TypeError, ValueError):
        return "12:00:00"
    if ts > 10_000_000_000:
        ts //= 1000
    from utils.date_utils import get_timezone

    dt = datetime.fromtimestamp(ts, tz=get_timezone(timezone))
    return dt.strftime("%H:%M:%S")


def _summarize_title(text: str, max_len: int = 120) -> str:
    one_line = re.sub(r"\s+", " ", text).strip()
    if not one_line:
        return "空消息"
    if len(one_line) <= max_len:
        return one_line
    return one_line[: max_len - 1] + "…"


def list_chat_messages(
    token: str,
    chat_id: str,
    *,
    start_ts: int,
    end_ts: int,
    base_url: str = DEFAULT_BASE_URL,
    page_size: int = 50,
    max_pages: int = 20,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """拉取指定 chat 在时间范围内的全部消息（分页）。"""
    url = f"{_api_base(base_url)}/open-apis/im/v1/messages"
    headers = {"Authorization": f"Bearer {token}"}
    items: list[dict[str, Any]] = []
    page_token: str | None = None
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)

    try:
        for _ in range(max_pages):
            params: dict[str, Any] = {
                "container_id_type": "chat",
                "container_id": chat_id,
                "start_time": str(start_ts),
                "end_time": str(end_ts),
                "page_size": min(max(page_size, 1), 50),
                "sort_type": "ByCreateTimeAsc",
            }
            if page_token:
                params["page_token"] = page_token

            resp = http.get(url, headers=headers, params=params)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != 0:
                raise FeishuOpenApiError(
                    f"拉取消息失败 chat={chat_id}: code={payload.get('code')} msg={payload.get('msg')}"
                )

            data = payload.get("data") or {}
            batch = data.get("items") or []
            if isinstance(batch, list):
                items.extend(m for m in batch if isinstance(m, dict))

            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
    finally:
        if own_client:
            http.close()

    return items


def messages_to_entries(
    messages: list[dict[str, Any]],
    *,
    chat_id: str,
    timezone: str,
    only_my_messages: bool = False,
    only_mention_me: bool = False,
    my_open_id: str = "",
    keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
) -> list[dict[str, Any]]:
    """将飞书原始消息转为采集 entry。"""
    keywords = keywords or []
    exclude_keywords = exclude_keywords or []
    entries: list[dict[str, Any]] = []

    for message in messages:
        sender = message.get("sender") or {}
        sender_id = sender.get("id") or ""
        if only_my_messages and my_open_id and sender_id != my_open_id:
            continue
        if only_mention_me and not _message_mentions_me(message, my_open_id):
            continue

        msg_type = message.get("msg_type") or ""
        body = message.get("body") or {}
        text = extract_message_text(msg_type, body if isinstance(body, dict) else {})
        if not _matches_keywords(text, keywords, exclude_keywords):
            continue

        message_id = message.get("message_id") or message.get("id") or ""
        create_time = message.get("create_time") or ""
        time_str = _create_time_to_hms(create_time, timezone)
        title = _summarize_title(text)
        sender_type = sender.get("sender_type") or ""
        detail_parts = [f"chat: {chat_id}"]
        if sender_id:
            detail_parts.append(f"sender: {sender_id} ({sender_type})")
        if msg_type:
            detail_parts.append(f"type: {msg_type}")
        if text and text != title:
            detail_parts.append(text)

        entries.append(
            {
                "id": message_id or f"{chat_id}-{create_time}",
                "time": time_str,
                "title": title,
                "detail": " | ".join(detail_parts),
                "chat_id": chat_id,
                "msg_type": msg_type,
                "sender_id": sender_id,
                "create_time": str(create_time),
                "raw": {
                    "message_id": message_id,
                    "msg_type": msg_type,
                    "chat_id": chat_id,
                    "sender": sender,
                    "mentions": message.get("mentions") or [],
                },
            }
        )

    return entries


def fetch_chat_entries_for_day(
    *,
    app_id: str,
    app_secret: str,
    chat_ids: list[str],
    date_str: str,
    timezone: str,
    base_url: str = DEFAULT_BASE_URL,
    only_my_messages: bool = False,
    only_mention_me: bool = False,
    my_open_id: str = "",
    keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    page_size: int = 50,
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    """按日期拉取多个会话的消息并合并为 entries。"""
    from utils.date_utils import day_bounds

    start_dt, end_dt = day_bounds(date_str, timezone)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp()) - 1

    all_entries: list[dict[str, Any]] = []
    with httpx.Client(timeout=30.0) as client:
        token = get_tenant_access_token(app_id, app_secret, base_url=base_url, client=client)
        for chat_id in chat_ids:
            chat_id = (chat_id or "").strip()
            if not chat_id:
                continue
            messages = list_chat_messages(
                token,
                chat_id,
                start_ts=start_ts,
                end_ts=end_ts,
                base_url=base_url,
                page_size=page_size,
                max_pages=max_pages,
                client=client,
            )
            all_entries.extend(
                messages_to_entries(
                    messages,
                    chat_id=chat_id,
                    timezone=timezone,
                    only_my_messages=only_my_messages,
                    only_mention_me=only_mention_me,
                    my_open_id=my_open_id,
                    keywords=keywords,
                    exclude_keywords=exclude_keywords,
                )
            )

    all_entries.sort(key=lambda e: (e.get("time") or "", e.get("id") or ""))
    return all_entries

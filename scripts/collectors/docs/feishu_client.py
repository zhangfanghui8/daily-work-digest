from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from collectors.chat.feishu_client import FeishuOpenApiError

DEFAULT_BASE_URL = "https://open.feishu.cn"
DEFAULT_TOKEN_CACHE = "data/.feishu_oauth.json"
DEFAULT_DOC_TYPES = ["DOC", "DOCX", "SHEET", "BITABLE", "WIKI", "MINDNOTE", "SLIDES", "FILE"]
OAUTH_SCOPE = "search:docs:read offline_access"
OAUTH_SCOPE_BASIC = "search:docs:read"
_HIGHLIGHT_TAG_RE = re.compile(r"<[^>]+>")


def _api_base(base_url: str) -> str:
    return base_url.rstrip("/")


def _strip_highlight(text: str) -> str:
    return _HIGHLIGHT_TAG_RE.sub("", text or "").strip()


def _resolve_app_credentials(docs_cfg: dict[str, Any], feishu_cfg: dict[str, Any]) -> tuple[str, str]:
    chat = feishu_cfg.get("chat") or {}
    app_id = (docs_cfg.get("app_id") or chat.get("app_id") or "").strip()
    app_secret = (docs_cfg.get("app_secret") or chat.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        raise FeishuOpenApiError(
            "缺少 app_id / app_secret，请在 feishu.docs 或 feishu.chat 中配置"
        )
    return app_id, app_secret


def oauth_scope(*, offline: bool = True) -> str:
    """OAuth 授权 scope；无 offline_access 权限时用 offline=False。"""
    return OAUTH_SCOPE if offline else OAUTH_SCOPE_BASIC


def oauth_authorize_url(
    app_id: str,
    redirect_uri: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    state: str = "daily-work-digest",
    scope: str = OAUTH_SCOPE,
) -> str:
    """生成飞书 OAuth 授权页 URL（用户浏览器打开）。"""
    encoded_redirect = quote(redirect_uri, safe="")
    encoded_scope = quote(scope, safe="")
    return (
        f"{_api_base(base_url)}/open-apis/authen/v1/authorize"
        f"?app_id={quote(app_id, safe='')}"
        f"&redirect_uri={encoded_redirect}"
        f"&scope={encoded_scope}"
        f"&state={quote(state, safe='')}"
    )


def exchange_code_for_tokens(
    app_id: str,
    app_secret: str,
    code: str,
    redirect_uri: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """用授权码换取 user_access_token / refresh_token。"""
    url = f"{_api_base(base_url)}/open-apis/authen/v2/oauth/token"
    payload = {
        "grant_type": "authorization_code",
        "client_id": app_id,
        "client_secret": app_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        resp = http.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise FeishuOpenApiError(
                f"OAuth 换 token 失败: code={data.get('code')} msg={data.get('msg')}"
            )
        return data
    finally:
        if own_client:
            http.close()


def refresh_user_tokens(
    app_id: str,
    app_secret: str,
    refresh_token: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """刷新 user_access_token（refresh_token 一次性，需保存新 refresh_token）。"""
    url = f"{_api_base(base_url)}/open-apis/authen/v2/oauth/token"
    payload = {
        "grant_type": "refresh_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "refresh_token": refresh_token,
    }
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        resp = http.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise FeishuOpenApiError(
                f"刷新 user_access_token 失败: code={data.get('code')} msg={data.get('msg')}"
            )
        return data
    finally:
        if own_client:
            http.close()


def resolve_token_cache_path(docs_cfg: dict[str, Any] | None = None) -> Path:
    """OAuth token 缓存路径（相对路径基于项目根目录）。"""
    docs_cfg = docs_cfg or {}
    path = (docs_cfg.get("token_cache") or DEFAULT_TOKEN_CACHE).strip()
    p = Path(path)
    if not p.is_absolute():
        from utils.paths import project_root

        p = project_root() / p
    return p


def _load_token_cache(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_token_cache(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_user_access_token(
    docs_cfg: dict[str, Any],
    feishu_cfg: dict[str, Any],
    *,
    client: httpx.Client | None = None,
) -> str:
    """解析可用的 user_access_token（直配 / refresh_token / token 缓存）。"""
    base_url = (docs_cfg.get("base_url") or DEFAULT_BASE_URL).strip()
    direct = (docs_cfg.get("user_access_token") or "").strip()
    if direct:
        return direct

    app_id, app_secret = _resolve_app_credentials(docs_cfg, feishu_cfg)
    cache_path = resolve_token_cache_path(docs_cfg)
    refresh_token = (docs_cfg.get("refresh_token") or "").strip()

    cached = _load_token_cache(cache_path)
    if not refresh_token:
        refresh_token = (cached.get("refresh_token") or "").strip()

    access_only = (cached.get("access_token") or "").strip()
    if access_only and not refresh_token:
        return access_only

    if not refresh_token:
        raise FeishuOpenApiError(
            "缺少 token。可选："
            "1) python scripts/feishu_oauth.py --login（用户仅在浏览器点同意）"
            "2) python scripts/feishu_oauth.py --paste-token <token>"
            "见 docs/飞书文档采集-用户指南.md"
        )

    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        data = refresh_user_tokens(
            app_id, app_secret, refresh_token, base_url=base_url, client=http
        )
        access_token = (data.get("access_token") or "").strip()
        if not access_token:
            raise FeishuOpenApiError("刷新 token 成功但响应缺少 access_token")

        new_refresh = (data.get("refresh_token") or refresh_token).strip()
        _save_token_cache(
            cache_path,
            {
                "access_token": access_token,
                "refresh_token": new_refresh,
                "expires_in": data.get("expires_in"),
                "refresh_token_expires_in": data.get("refresh_token_expires_in"),
            },
        )
        return access_token
    finally:
        if own_client:
            http.close()


def search_my_edited_docs(
    user_access_token: str,
    *,
    start_ts: int,
    end_ts: int,
    base_url: str = DEFAULT_BASE_URL,
    query: str = "",
    doc_types: list[str] | None = None,
    page_size: int = 20,
    max_pages: int = 10,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    """搜索指定时间范围内「我编辑过的」云文档与 Wiki（L1 元数据）。"""
    url = f"{_api_base(base_url)}/open-apis/search/v2/doc_wiki/search"
    headers = {
        "Authorization": f"Bearer {user_access_token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    time_range = {"start": start_ts, "end": end_ts}
    filter_body: dict[str, Any] = {
        "my_edit_time": time_range,
        "sort_type": "EDIT_TIME_ASC",
    }
    if doc_types:
        filter_body["doc_types"] = doc_types

    seen_tokens: set[str] = set()
    results: list[dict[str, Any]] = []
    page_token: str | None = None
    own_client = client is None
    http = client or httpx.Client(timeout=30.0)

    try:
        for _ in range(max_pages):
            body: dict[str, Any] = {
                "query": query,
                "doc_filter": dict(filter_body),
                "wiki_filter": dict(filter_body),
                "page_size": min(max(page_size, 1), 20),
            }
            if page_token:
                body["page_token"] = page_token

            resp = http.post(url, headers=headers, json=body)
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("code") != 0:
                raise FeishuOpenApiError(
                    f"搜索云文档失败: code={payload.get('code')} msg={payload.get('msg')}"
                )

            data = payload.get("data") or {}
            for unit in data.get("res_units") or []:
                if not isinstance(unit, dict):
                    continue
                meta = unit.get("result_meta") or {}
                token = (meta.get("token") or "").strip()
                dedupe_key = token or f"{unit.get('entity_type')}-{meta.get('url')}"
                if dedupe_key in seen_tokens:
                    continue
                seen_tokens.add(dedupe_key)
                results.append(unit)

            if not data.get("has_more"):
                break
            page_token = data.get("page_token")
            if not page_token:
                break
    finally:
        if own_client:
            http.close()

    return results


def _timestamp_to_hms(ts: int, timezone: str) -> str:
    from utils.date_utils import get_timezone

    dt = datetime.fromtimestamp(ts, tz=get_timezone(timezone))
    return dt.strftime("%H:%M:%S")


def search_results_to_entries(
    units: list[dict[str, Any]],
    *,
    timezone: str,
) -> list[dict[str, Any]]:
    """将搜索 API 结果转为 L1 entry（不含全文）。"""
    entries: list[dict[str, Any]] = []
    for unit in units:
        meta = unit.get("result_meta") or {}
        token = (meta.get("token") or "").strip()
        title = _strip_highlight(unit.get("title_highlighted") or "") or "无标题文档"
        summary = _strip_highlight(unit.get("summary_highlighted") or "")
        entity_type = unit.get("entity_type") or ""
        doc_type = meta.get("doc_types") or meta.get("file_type") or entity_type
        url = (meta.get("url") or "").strip()
        update_time = meta.get("update_time")
        try:
            update_ts = int(update_time)
        except (TypeError, ValueError):
            update_ts = 0

        edit_user_name = meta.get("edit_user_name") or ""
        edit_user_id = meta.get("edit_user_id") or ""
        owner_name = meta.get("owner_name") or ""

        detail_parts: list[str] = []
        if doc_type:
            detail_parts.append(f"type: {doc_type}")
        if edit_user_name:
            detail_parts.append(f"editor: {edit_user_name}")
        elif edit_user_id:
            detail_parts.append(f"editor_id: {edit_user_id}")
        if owner_name:
            detail_parts.append(f"owner: {owner_name}")
        if summary:
            detail_parts.append(f"summary: {summary[:120]}")

        entries.append(
            {
                "id": token or f"feishu-doc-{len(entries)+1}",
                "time": _timestamp_to_hms(update_ts, timezone) if update_ts else "12:00:00",
                "title": title,
                "detail": " | ".join(detail_parts),
                "url": url,
                "doc_type": doc_type,
                "entity_type": entity_type,
                "token": token,
                "update_time": update_ts,
                "edit_user_id": edit_user_id,
                "edit_user_name": edit_user_name,
                "owner_name": owner_name,
                "summary": summary[:200] if summary else "",
                "raw": {
                    "token": token,
                    "entity_type": entity_type,
                    "doc_type": doc_type,
                    "url": url,
                    "update_time": update_ts,
                },
            }
        )

    entries.sort(key=lambda e: (e.get("time") or "", e.get("title") or ""))
    return entries


def _filter_units_by_update_time(
    units: list[dict[str, Any]],
    *,
    start_ts: int,
    end_ts: int,
) -> list[dict[str, Any]]:
    """按 result_meta.update_time 筛到目标日历日（秒级，含起止）。"""
    filtered: list[dict[str, Any]] = []
    for unit in units:
        meta = unit.get("result_meta") or {}
        try:
            update_ts = int(meta.get("update_time") or 0)
        except (TypeError, ValueError):
            continue
        if start_ts <= update_ts <= end_ts:
            filtered.append(unit)
    return filtered


def fetch_doc_entries_for_day(
    docs_cfg: dict[str, Any],
    feishu_cfg: dict[str, Any],
    *,
    date_str: str,
    timezone: str,
) -> list[dict[str, Any]]:
    """按日期拉取「我编辑过的」飞书文档 L1 元数据。"""
    from utils.date_utils import day_bounds

    base_url = (docs_cfg.get("base_url") or DEFAULT_BASE_URL).strip()
    start_dt, end_dt = day_bounds(date_str, timezone)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp()) - 1

    include_types = docs_cfg.get("include_types") or DEFAULT_DOC_TYPES
    doc_types = [str(t).strip().upper() for t in include_types if str(t).strip()]
    # 飞书搜索 my_edit_time 窄窗口常漏刚编辑文档；向前扩窗再按 update_time 本地过滤
    padding_days = int(docs_cfg.get("search_padding_days") or 7)
    api_start_ts = start_ts - max(padding_days, 1) * 86400

    with httpx.Client(timeout=30.0) as client:
        user_token = resolve_user_access_token(docs_cfg, feishu_cfg, client=client)
        units = search_my_edited_docs(
            user_token,
            start_ts=api_start_ts,
            end_ts=end_ts,
            base_url=base_url,
            query=(docs_cfg.get("query") or "").strip(),
            doc_types=doc_types or None,
            page_size=int(docs_cfg.get("page_size") or 20),
            max_pages=int(docs_cfg.get("max_pages") or 10),
            client=client,
        )

    units = _filter_units_by_update_time(units, start_ts=start_ts, end_ts=end_ts)
    return search_results_to_entries(units, timezone=timezone)

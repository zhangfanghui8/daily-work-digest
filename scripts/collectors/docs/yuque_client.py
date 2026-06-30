from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

import httpx

DEFAULT_API_BASE = "https://www.yuque.com/api/v2"
DEFAULT_WEB_API_BASE = "https://www.yuque.com/api"
USER_AGENT = "daily-work-digest"
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

AuthMode = Literal["token", "cookie"]


class YuqueOpenApiError(RuntimeError):
    """语雀 Open API 调用失败。"""


@dataclass(frozen=True)
class YuqueAuth:
    mode: AuthMode
    value: str

    @property
    def is_token(self) -> bool:
        return self.mode == "token"

    @property
    def is_cookie(self) -> bool:
        return self.mode == "cookie"


def _api_base(docs_cfg: dict[str, Any]) -> str:
    return (docs_cfg.get("api_base") or DEFAULT_API_BASE).rstrip("/")


def resolve_auth_mode(docs_cfg: dict[str, Any]) -> AuthMode:
    mode = (docs_cfg.get("auth_mode") or "token").strip().lower()
    if mode not in ("token", "cookie"):
        raise YuqueOpenApiError(
            f"无效的 yuque.docs.auth_mode: {mode!r}，应为 token 或 cookie"
        )
    return mode  # type: ignore[return-value]


def normalize_cookie(raw: str) -> str:
    """将裸 session 值或完整 Cookie 串规范化为 HTTP Cookie 头。"""
    first_line = raw.strip().splitlines()[0].strip() if raw.strip() else ""
    if not first_line:
        return ""

    if ";" in first_line or first_line.startswith("lang="):
        return first_line
    if first_line.startswith("_yuque_session=") or "yuque_ctoken=" in first_line:
        return first_line

    return f"_yuque_session={first_line}"


def resolve_token(docs_cfg: dict[str, Any]) -> str:
    """从 config.yaml 的 yuque.docs.token 解析 Token。"""
    token = (docs_cfg.get("token") or "").strip()
    if token:
        return token

    raise YuqueOpenApiError(
        "缺少语雀 Token，请在 config.yaml 的 yuque.docs.token 中配置。"
        "见 docs/语雀文档采集-用户指南.md"
    )


def resolve_cookie(docs_cfg: dict[str, Any]) -> str:
    """从 config.yaml 的 yuque.docs.cookie 解析 Cookie。"""
    cookie = normalize_cookie(docs_cfg.get("cookie") or "")
    if cookie:
        return cookie

    raise YuqueOpenApiError(
        "缺少语雀 Cookie，请在 config.yaml 的 yuque.docs.cookie 中配置。"
        "见 docs/语雀文档采集-用户指南.md"
    )


def _web_api_base(docs_cfg: dict[str, Any]) -> str:
    return (docs_cfg.get("web_api_base") or DEFAULT_WEB_API_BASE).rstrip("/")


def _cookie_parts(cookie: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for part in cookie.split(";"):
        part = part.strip()
        if "=" in part:
            key, value = part.split("=", 1)
            parts[key.strip()] = value.strip()
    return parts


def resolve_auth(docs_cfg: dict[str, Any]) -> YuqueAuth:
    """按 auth_mode 解析认证State 或 Cookie 认证信息。"""
    mode = resolve_auth_mode(docs_cfg)
    if mode == "cookie":
        return YuqueAuth(mode="cookie", value=resolve_cookie(docs_cfg))
    return YuqueAuth(mode="token", value=resolve_token(docs_cfg))


def _headers(auth: YuqueAuth) -> dict[str, str]:
    if auth.is_token:
        return {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "X-Auth-Token": auth.value,
        }

    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "application/json",
        "Referer": "https://www.yuque.com/",
        "Cookie": auth.value,
    }
    ctoken = _cookie_parts(auth.value).get("yuque_ctoken", "")
    if ctoken:
        headers["X-Csrf-Token"] = ctoken
    return headers


def _request_json(
    method: str,
    url: str,
    auth: YuqueAuth,
    *,
    params: dict[str, Any] | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    own_client = client is None
    http = client or httpx.Client(timeout=30.0, follow_redirects=True)
    try:
        resp = http.request(method, url, headers=_headers(auth), params=params)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise YuqueOpenApiError(f"语雀 API 响应格式异常: {url}")
        return payload
    except httpx.HTTPStatusError as exc:
        hint = ""
        if exc.response.status_code == 401:
            if auth.is_cookie:
                hint = "（Cookie 可能已过期，请从浏览器重新复制）"
            else:
                hint = "（Token 可能无效或已撤销）"
        raise YuqueOpenApiError(
            f"语雀 API HTTP {exc.response.status_code}: {url} — "
            f"{exc.response.text[:200]}{hint}"
        ) from exc
    finally:
        if own_client:
            http.close()


def _list_mine_books(
    auth: YuqueAuth,
    *,
    web_api_base: str,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    payload = _request_json("GET", f"{web_api_base}/mine/books", auth, client=client)
    data = payload.get("data")
    return data if isinstance(data, list) else []


def _book_namespace(book: dict[str, Any]) -> str:
    user = book.get("user") or {}
    login = user.get("login") if isinstance(user, dict) else ""
    slug = (book.get("slug") or "").strip()
    if login and slug:
        return f"{login}/{slug}"
    return str(book.get("id") or "")


def _resolve_book_ref(
    namespace: str,
    auth: YuqueAuth,
    *,
    web_api_base: str,
    client: httpx.Client | None = None,
) -> tuple[str, str]:
    """Cookie 模式：namespace 或 book_id → (book_id, namespace)。"""
    ns = namespace.strip().strip("/")
    if ns.isdigit():
        return ns, ns

    if "/" not in ns:
        raise YuqueOpenApiError(
            f"Cookie 模式下 repos 需为 login/slug 或数字 book_id，当前: {namespace!r}"
        )

    login, slug = ns.split("/", 1)
    for book in _list_mine_books(auth, web_api_base=web_api_base, client=client):
        if not isinstance(book, dict):
            continue
        if str(book.get("slug") or "") != slug:
            continue
        user = book.get("user") or {}
        book_login = user.get("login") if isinstance(user, dict) else ""
        if book_login and book_login != login:
            continue
        book_id = str(book.get("id") or "")
        if book_id:
            return book_id, ns

    raise YuqueOpenApiError(
        f"未在账号知识库列表中找到 {namespace}。"
        "请运行 python scripts/debug_yuque_docs.py --list-repos 查看可用 namespace"
    )


def get_current_user(
    auth: YuqueAuth,
    *,
    api_base: str,
    web_api_base: str = DEFAULT_WEB_API_BASE,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    if auth.is_cookie:
        payload = _request_json(
            "GET", f"{web_api_base.rstrip('/')}/mine", auth, client=client
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise YuqueOpenApiError("获取语雀用户信息失败")
        return {
            "id": data.get("id"),
            "login": data.get("login"),
            "name": data.get("name"),
        }

    payload = _request_json("GET", f"{api_base}/user", auth, client=client)
    user = payload.get("data")
    if not isinstance(user, dict):
        raise YuqueOpenApiError("获取语雀用户信息失败")
    return user


def list_user_repos(
    login: str,
    auth: YuqueAuth,
    *,
    api_base: str,
    web_api_base: str = DEFAULT_WEB_API_BASE,
    offset: int = 0,
    limit: int = 100,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    if auth.is_cookie:
        books = _list_mine_books(auth, web_api_base=web_api_base, client=client)
        sliced = books[offset : offset + min(limit, 100)]
        repos: list[dict[str, Any]] = []
        for book in sliced:
            if not isinstance(book, dict):
                continue
            repos.append(
                {
                    "id": book.get("id"),
                    "slug": book.get("slug") or "",
                    "name": book.get("name") or "",
                    "user": book.get("user") or {},
                }
            )
        return repos

    payload = _request_json(
        "GET",
        f"{api_base}/users/{login}/repos",
        auth,
        params={"offset": offset, "limit": min(limit, 100)},
        client=client,
    )
    data = payload.get("data")
    return data if isinstance(data, list) else []


def list_repo_docs(
    namespace: str,
    auth: YuqueAuth,
    *,
    api_base: str,
    web_api_base: str = DEFAULT_WEB_API_BASE,
    offset: int = 0,
    limit: int = 100,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    if auth.is_cookie:
        book_id, _ = _resolve_book_ref(
            namespace, auth, web_api_base=web_api_base, client=client
        )
        payload = _request_json(
            "GET",
            f"{web_api_base.rstrip('/')}/books/{book_id}/docs",
            auth,
            params={"offset": offset, "limit": min(limit, 100)},
            client=client,
        )
        data = payload.get("data")
        return data if isinstance(data, list) else []

    ns = namespace.strip().strip("/")
    payload = _request_json(
        "GET",
        f"{api_base}/repos/{ns}/docs",
        auth,
        params={"offset": offset, "limit": min(limit, 100)},
        client=client,
    )
    data = payload.get("data")
    return data if isinstance(data, list) else []


def fetch_all_repo_docs(
    namespace: str,
    auth: YuqueAuth,
    *,
    api_base: str,
    web_api_base: str = DEFAULT_WEB_API_BASE,
    page_limit: int = 100,
    max_pages: int = 20,
    client: httpx.Client | None = None,
) -> list[dict[str, Any]]:
    all_docs: list[dict[str, Any]] = []
    offset = 0
    limit = min(max(page_limit, 1), 100)
    for _ in range(max_pages):
        batch = list_repo_docs(
            namespace,
            auth,
            api_base=api_base,
            web_api_base=web_api_base,
            offset=offset,
            limit=limit,
            client=client,
        )
        if not batch:
            break
        all_docs.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return all_docs


def normalize_repos(repos_cfg: list[Any] | None) -> list[str]:
    namespaces: list[str] = []
    for item in repos_cfg or []:
        if isinstance(item, str) and item.strip():
            namespaces.append(item.strip().strip("/"))
        elif isinstance(item, dict):
            ns = (item.get("namespace") or item.get("repo") or "").strip().strip("/")
            if ns:
                namespaces.append(ns)
    return namespaces


def repo_namespace_from_item(repo: dict[str, Any], fallback_login: str = "") -> str:
    user_obj = repo.get("user") or {}
    login = user_obj.get("login") if isinstance(user_obj, dict) else fallback_login
    slug = (repo.get("slug") or "").strip()
    if login and slug:
        return f"{login}/{slug}"
    book_id = repo.get("id")
    return str(book_id) if book_id else ""


def resolve_repos(
    docs_cfg: dict[str, Any],
    auth: YuqueAuth,
    *,
    api_base: str,
    web_api_base: str,
    client: httpx.Client,
) -> tuple[list[str], bool]:
    """解析要扫描的知识库列表。repos 留空时自动发现账号下知识库。"""
    configured = normalize_repos(docs_cfg.get("repos"))
    if configured:
        return configured, False

    if docs_cfg.get("auto_repos") is False:
        raise YuqueOpenApiError(
            "yuque.docs.repos 为空且 auto_repos 已关闭。"
            "请填写 repos，或将 auto_repos 设为 true（默认）以自动扫描"
        )

    max_auto = int(docs_cfg.get("max_auto_repos") or 50)
    namespaces: list[str] = []

    if auth.is_cookie:
        for book in _list_mine_books(auth, web_api_base=web_api_base, client=client):
            if not isinstance(book, dict):
                continue
            ns = _book_namespace(book)
            if ns:
                namespaces.append(ns)
    else:
        user = get_current_user(
            auth, api_base=api_base, web_api_base=web_api_base, client=client
        )
        login = (user.get("login") or "").strip()
        if not login:
            raise YuqueOpenApiError("无法获取语雀用户 login")
        offset = 0
        while len(namespaces) < max_auto:
            batch = list_user_repos(
                login,
                auth,
                api_base=api_base,
                web_api_base=web_api_base,
                offset=offset,
                limit=100,
                client=client,
            )
            if not batch:
                break
            for repo in batch:
                if not isinstance(repo, dict):
                    continue
                ns = repo_namespace_from_item(repo, login)
                if ns:
                    namespaces.append(ns)
            if len(batch) < 100:
                break
            offset += 100

    if not namespaces:
        raise YuqueOpenApiError("未找到可扫描的知识库")

    return namespaces[:max_auto], True


def _parse_yuque_datetime(value: str | None, timezone: str) -> datetime | None:
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        from dateutil import parser as date_parser

        dt = date_parser.parse(str(value))
    if dt.tzinfo is None:
        from utils.date_utils import get_timezone

        dt = dt.replace(tzinfo=get_timezone(timezone))
    return dt


def _doc_edit_datetimes(
    doc: dict[str, Any],
    *,
    timezone: str,
    use_content_updated_at: bool,
    also_use_updated_at: bool,
) -> list[datetime]:
    dts: list[datetime] = []
    if use_content_updated_at:
        dt = _parse_yuque_datetime(doc.get("content_updated_at"), timezone)
        if dt:
            dts.append(dt)
    if also_use_updated_at:
        dt = _parse_yuque_datetime(doc.get("updated_at"), timezone)
        if dt:
            dts.append(dt)
    return dts


def _doc_matches_day(
    doc: dict[str, Any],
    target: date,
    *,
    timezone: str,
    use_content_updated_at: bool,
    also_use_updated_at: bool,
) -> datetime | None:
    from utils.date_utils import get_timezone

    tz = get_timezone(timezone)
    for dt in _doc_edit_datetimes(
        doc,
        timezone=timezone,
        use_content_updated_at=use_content_updated_at,
        also_use_updated_at=also_use_updated_at,
    ):
        if dt.astimezone(tz).date() == target:
            return dt.astimezone(tz)
    return None


def _build_doc_url(doc: dict[str, Any], namespace: str) -> str:
    if doc.get("url"):
        return str(doc["url"]).strip()
    slug = (doc.get("slug") or "").strip()
    if not slug:
        return ""
    book = doc.get("book") or {}
    if isinstance(book, dict):
        user = book.get("user") or {}
        if isinstance(user, dict) and user.get("login") and book.get("slug"):
            return f"https://www.yuque.com/{user['login']}/{book['slug']}/{slug}"
    if "/" in namespace:
        return f"https://www.yuque.com/{namespace}/{slug}"
    return f"https://www.yuque.com/go/doc/{doc.get('id', slug)}"


def _editor_name(doc: dict[str, Any]) -> str:
    editor = doc.get("last_editor") or {}
    if isinstance(editor, dict):
        return (editor.get("name") or editor.get("login") or "").strip()
    return ""


def docs_to_entries(
    docs: list[dict[str, Any]],
    *,
    namespace: str,
    timezone: str,
    date_str: str,
    use_content_updated_at: bool,
    also_use_updated_at: bool,
    only_my_edits: bool,
    my_user_id: int | None,
) -> list[dict[str, Any]]:
    target = date.fromisoformat(date_str)
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for doc in docs:
        if only_my_edits and my_user_id is not None:
            editor_id = doc.get("last_editor_id")
            try:
                if int(editor_id) != int(my_user_id):
                    continue
            except (TypeError, ValueError):
                continue

        matched_dt = _doc_matches_day(
            doc,
            target,
            timezone=timezone,
            use_content_updated_at=use_content_updated_at,
            also_use_updated_at=also_use_updated_at,
        )
        if matched_dt is None:
            continue

        doc_id = str(doc.get("id") or doc.get("slug") or "")
        dedupe = f"{namespace}:{doc_id}"
        if dedupe in seen_ids:
            continue
        seen_ids.add(dedupe)

        title = (doc.get("title") or "").strip() or "无标题文档"
        url = _build_doc_url(doc, namespace)
        editor = _editor_name(doc)
        detail_parts = [f"repo: {namespace}"]
        if editor:
            detail_parts.append(f"editor: {editor}")
        fmt = doc.get("format") or ""
        if fmt:
            detail_parts.append(f"format: {fmt}")

        entries.append(
            {
                "id": doc_id or f"yuque-{len(entries)+1}",
                "time": matched_dt.strftime("%H:%M:%S"),
                "title": title,
                "detail": " | ".join(detail_parts),
                "url": url,
                "book_namespace": namespace,
                "slug": doc.get("slug") or "",
                "format": fmt,
                "content_updated_at": doc.get("content_updated_at") or "",
                "updated_at": doc.get("updated_at") or "",
                "raw": {
                    "id": doc.get("id"),
                    "slug": doc.get("slug"),
                    "book_id": doc.get("book_id"),
                    "namespace": namespace,
                },
            }
        )

    entries.sort(key=lambda e: (e.get("time") or "", e.get("title") or ""))
    return entries


def fetch_doc_entries_for_day(
    docs_cfg: dict[str, Any],
    *,
    date_str: str,
    timezone: str,
) -> dict[str, Any]:
    """按日期拉取语雀知识库文档 L1 元数据。"""
    auth = resolve_auth(docs_cfg)
    api_base = _api_base(docs_cfg)
    web_api_base = _web_api_base(docs_cfg)

    only_my_edits = bool(docs_cfg.get("only_my_edits", True))
    use_content_updated_at = bool(docs_cfg.get("use_content_updated_at", True))
    also_use_updated_at = bool(docs_cfg.get("also_use_updated_at", True))
    page_limit = int(docs_cfg.get("page_limit") or 100)
    max_pages = int(docs_cfg.get("max_pages") or 20)

    all_entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    namespaces: list[str] = []
    repos_auto = False

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        namespaces, repos_auto = resolve_repos(
            docs_cfg,
            auth,
            api_base=api_base,
            web_api_base=web_api_base,
            client=client,
        )

        my_user_id: int | None = None
        if only_my_edits:
            user = get_current_user(
                auth, api_base=api_base, web_api_base=web_api_base, client=client
            )
            try:
                my_user_id = int(user.get("id"))
            except (TypeError, ValueError):
                auth_label = "Cookie" if auth.is_cookie else "Token"
                raise YuqueOpenApiError(
                    f"无法解析语雀用户 ID，请关闭 only_my_edits 或检查 {auth_label}"
                ) from None

        for namespace in namespaces:
            docs = fetch_all_repo_docs(
                namespace,
                auth,
                api_base=api_base,
                web_api_base=web_api_base,
                page_limit=page_limit,
                max_pages=max_pages,
                client=client,
            )
            batch = docs_to_entries(
                docs,
                namespace=namespace,
                timezone=timezone,
                date_str=date_str,
                use_content_updated_at=use_content_updated_at,
                also_use_updated_at=also_use_updated_at,
                only_my_edits=only_my_edits,
                my_user_id=my_user_id,
            )
            for entry in batch:
                key = f"{entry.get('book_namespace')}:{entry.get('id')}"
                if key in seen:
                    continue
                seen.add(key)
                all_entries.append(entry)

    all_entries.sort(key=lambda e: (e.get("time") or "", e.get("title") or ""))
    return {
        "entries": all_entries,
        "repos": namespaces,
        "repos_auto": repos_auto,
    }

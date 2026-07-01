from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_TOKEN_CACHE = "data/.zentao_token.json"
MAX_AUTO_PRODUCTS = 30
MAX_AUTO_PROJECTS = 30
MAX_AUTO_EXECUTIONS = 50
MAX_PAGES = 20
PAGE_SIZE = 100

BUG_BROWSE_TYPES = ("assignedtome", "openedbyme", "resolvedbyme", "assignedbyme")
STORY_BROWSE_TYPES = ("assignedtome", "openedbyme", "reviewedbyme")
TASK_BROWSE_TYPES = ("assignedtome", "openedbyme", "finishedbyme", "closedbyme")


class ZenTaoApiError(RuntimeError):
    """禅道 Open API 调用失败。"""

    def __init__(self, message: str, *, code: str = "") -> None:
        super().__init__(message)
        self.code = code


AUTH_REQUIRED = "auth_required"
TOKEN_EXPIRED = "token_expired"


def resolve_token_cache_path(zentao_cfg: dict[str, Any]) -> Path:
    from utils.paths import project_root

    raw = (zentao_cfg.get("token_cache") or DEFAULT_TOKEN_CACHE).strip()
    path = Path(raw)
    if not path.is_absolute():
        path = project_root() / path
    return path


def normalize_base_url(base_url: str) -> str:
    return (base_url or "").strip().rstrip("/")


def load_token_cache(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(data, dict) and (data.get("token") or "").strip():
        return data
    return None


def save_token_cache(path: Path, *, token: str, account: str, base_url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "token": token,
                "account": account,
                "base_url": normalize_base_url(base_url),
                "obtained_at": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def login(
    base_url: str,
    account: str,
    password: str,
    *,
    client: httpx.Client | None = None,
) -> str:
    """登录禅道，优先 v2，失败则尝试 v1 tokens。"""
    base = normalize_base_url(base_url)
    account = account.strip()
    password = password.strip()
    if not base or not account or not password:
        raise ZenTaoApiError("base_url、账号、密码不能为空")

    own_client = client is None
    http = client or httpx.Client(timeout=30.0)
    try:
        token = _login_v2(http, base, account, password)
        if token:
            return token
        return _login_v1(http, base, account, password)
    finally:
        if own_client:
            http.close()


def _login_v2(http: httpx.Client, base: str, account: str, password: str) -> str:
    url = f"{base}/api.php/v2/users/login"
    try:
        resp = http.post(url, json={"account": account, "password": password})
    except httpx.HTTPError as exc:
        raise ZenTaoApiError(f"登录请求失败: {exc}") from exc
    if resp.status_code == 404:
        return ""
    payload = _parse_json(resp)
    if payload.get("status") == "success" and payload.get("token"):
        return str(payload["token"])
    if payload.get("token"):
        return str(payload["token"])
    if resp.status_code >= 400:
        return ""
    raise ZenTaoApiError(
        f"登录失败: {payload.get('msg') or payload.get('message') or resp.text[:200]}"
    )


def _login_v1(http: httpx.Client, base: str, account: str, password: str) -> str:
    url = f"{base}/api.php/v1/tokens"
    resp = http.post(url, json={"account": account, "password": password})
    payload = _parse_json(resp)
    token = payload.get("token")
    if token:
        return str(token)
    raise ZenTaoApiError(f"登录失败: {payload.get('msg') or payload.get('error') or resp.text[:200]}")


def _parse_json(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except json.JSONDecodeError as exc:
        raise ZenTaoApiError(f"非 JSON 响应 HTTP {resp.status_code}: {resp.text[:200]}") from exc
    if isinstance(data, dict):
        return data
    return {}


def _api_get(
    http: httpx.Client,
    base: str,
    token: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{base}/api.php/v2{path}"
    headers = {"Token": token, "Content-Type": "application/json"}
    resp = http.get(url, headers=headers, params=params or {})
    if resp.status_code == 401:
        raise ZenTaoApiError(
            "Token 无效或已过期",
            code=TOKEN_EXPIRED,
        )
    if resp.status_code == 404:
        return {}
    payload = _parse_json(resp)
    if payload.get("status") == "fail":
        raise ZenTaoApiError(str(payload.get("msg") or payload.get("message") or "请求失败"))
    return payload


def _extract_list(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    if isinstance(payload.get("data"), dict):
        data = payload["data"]
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _paginate(
    http: httpx.Client,
    base: str,
    token: str,
    path: str,
    *,
    list_keys: tuple[str, ...],
    extra_params: dict[str, Any] | None = None,
    max_pages: int = MAX_PAGES,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    params = dict(extra_params or {})
    params.setdefault("recPerPage", PAGE_SIZE)
    for page in range(1, max_pages + 1):
        params["pageID"] = page
        payload = _api_get(http, base, token, path, params=params)
        batch = _extract_list(payload, *list_keys)
        if not batch:
            break
        items.extend(batch)
        total = payload.get("total")
        if isinstance(total, int) and len(items) >= total:
            break
        if len(batch) < int(params.get("recPerPage") or PAGE_SIZE):
            break
    return items


def _date_part(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text.startswith("0000"):
        return ""
    return text[:10]


def _time_part(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 19:
        try:
            dt = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
            return dt.strftime("%H:%M:%S")
        except ValueError:
            pass
    return "12:00:00"


def _pick_action_on_day(item: dict[str, Any], date_str: str) -> tuple[str, str] | None:
    """返回 (action, datetime_str) 若当日有状态变更。"""
    checks: list[tuple[str, str]] = [
        ("opened", "openedDate"),
        ("resolved", "resolvedDate"),
        ("closed", "closedDate"),
        ("finished", "finishedDate"),
        ("assigned", "assignedDate"),
        ("edited", "lastEditedDate"),
    ]
    for action, date_field in checks:
        raw = str(item.get(date_field) or "").strip()
        if _date_part(raw) == date_str:
            return action, raw
    return None


def _object_url(base: str, object_type: str, object_id: Any) -> str:
    oid = str(object_id or "").strip()
    if not oid:
        return ""
    module_map = {"bug": "bug", "story": "story", "task": "task"}
    module = module_map.get(object_type, object_type)
    return f"{base}/index.php?m={module}&f=view&{module}ID={oid}"


def _action_label(action: str, object_type: str) -> str:
    labels = {
        "opened": "新建",
        "resolved": "解决",
        "closed": "关闭",
        "finished": "完成",
        "assigned": "指派",
        "edited": "更新",
    }
    type_labels = {"bug": "Bug", "story": "需求", "task": "任务"}
    return f"{labels.get(action, action)}{type_labels.get(object_type, object_type)}"


def _item_to_entry(
    item: dict[str, Any],
    *,
    object_type: str,
    date_str: str,
    base_url: str,
    scope: str,
) -> dict[str, Any] | None:
    picked = _pick_action_on_day(item, date_str)
    if not picked:
        return None
    action, when = picked
    object_id = item.get("id") or item.get("bugID") or item.get("storyID") or item.get("taskID")
    title_text = (
        item.get("title")
        or item.get("name")
        or item.get("storyTitle")
        or f"#{object_id}"
    )
    prefix = _action_label(action, object_type)
    status = item.get("status") or item.get("subStatus") or ""
    detail_parts = [f"scope: {scope}"]
    if status:
        detail_parts.append(f"status: {status}")
    if item.get("severity"):
        detail_parts.append(f"severity: {item.get('severity')}")
    if item.get("pri"):
        detail_parts.append(f"pri: {item.get('pri')}")

    return {
        "id": f"zentao-{object_type}-{object_id}-{action}-{date_str}",
        "time": _time_part(when),
        "title": f"{prefix} #{object_id} {title_text}".strip(),
        "detail": " | ".join(detail_parts),
        "url": _object_url(base_url, object_type, object_id),
        "object_type": object_type,
        "object_id": str(object_id or ""),
        "action": action,
        "scope": scope,
        "raw": {
            "id": object_id,
            "title": title_text,
            "status": status,
            "action": action,
            "scope": scope,
        },
    }


def _dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for entry in entries:
        key = entry.get("id") or ""
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    result.sort(key=lambda e: (e.get("time") or "", e.get("id") or ""))
    return result


def _fetch_bugs_for_product(
    http: httpx.Client,
    base: str,
    token: str,
    product_id: Any,
    *,
    date_str: str,
    account: str,
    only_my: bool,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    scope = f"product/{product_id}"
    for browse_type in BUG_BROWSE_TYPES:
        path = f"/products/{product_id}/bugs"
        try:
            items = _paginate(
                http,
                base,
                token,
                path,
                list_keys=("bugs",),
                extra_params={"browseType": browse_type},
                max_pages=5,
            )
        except ZenTaoApiError:
            continue
        for item in items:
            entry = _item_to_entry(
                item,
                object_type="bug",
                date_str=date_str,
                base_url=base,
                scope=scope,
            )
            if entry:
                entries.append(entry)
    return entries


def _fetch_stories_for_project(
    http: httpx.Client,
    base: str,
    token: str,
    project_id: Any,
    *,
    date_str: str,
    account: str,
    only_my: bool,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    scope = f"project/{project_id}"
    for browse_type in STORY_BROWSE_TYPES:
        path = f"/projects/{project_id}/stories"
        try:
            items = _paginate(
                http,
                base,
                token,
                path,
                list_keys=("stories",),
                extra_params={"browseType": browse_type},
                max_pages=5,
            )
        except ZenTaoApiError:
            continue
        for item in items:
            entry = _item_to_entry(
                item,
                object_type="story",
                date_str=date_str,
                base_url=base,
                scope=scope,
            )
            if entry:
                entries.append(entry)
    return entries


def _fetch_tasks_for_execution(
    http: httpx.Client,
    base: str,
    token: str,
    execution_id: Any,
    *,
    date_str: str,
    account: str,
    only_my: bool,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    scope = f"execution/{execution_id}"
    for browse_type in TASK_BROWSE_TYPES:
        path = f"/executions/{execution_id}/tasks"
        try:
            items = _paginate(
                http,
                base,
                token,
                path,
                list_keys=("tasks",),
                extra_params={"browseType": browse_type},
                max_pages=5,
            )
        except ZenTaoApiError:
            continue
        for item in items:
            entry = _item_to_entry(
                item,
                object_type="task",
                date_str=date_str,
                base_url=base,
                scope=scope,
            )
            if entry:
                entries.append(entry)
    return entries


def _list_products(http: httpx.Client, base: str, token: str) -> list[dict[str, Any]]:
    try:
        return _paginate(
            http,
            base,
            token,
            "/products",
            list_keys=("products",),
            extra_params={"browseType": "all"},
            max_pages=3,
        )[:MAX_AUTO_PRODUCTS]
    except ZenTaoApiError:
        return []


def _list_projects(http: httpx.Client, base: str, token: str) -> list[dict[str, Any]]:
    try:
        return _paginate(
            http,
            base,
            token,
            "/projects",
            list_keys=("projects",),
            extra_params={"browseType": "undone"},
            max_pages=3,
        )[:MAX_AUTO_PROJECTS]
    except ZenTaoApiError:
        return []


def _list_executions(http: httpx.Client, base: str, token: str, project_id: Any) -> list[dict[str, Any]]:
    try:
        return _paginate(
            http,
            base,
            token,
            f"/projects/{project_id}/executions",
            list_keys=("executions",),
            extra_params={"browseType": "undone"},
            max_pages=3,
        )
    except ZenTaoApiError:
        return []


def fetch_entries_for_day(
    zentao_cfg: dict[str, Any],
    *,
    date_str: str,
    token: str,
    account: str,
    base_url: str,
) -> dict[str, Any]:
    """采集指定日期禅道 Bug / 需求 / 任务变更（L1）。"""
    base = normalize_base_url(base_url)
    only_my = bool(zentao_cfg.get("only_my_activity", True))
    product_ids = [p for p in (zentao_cfg.get("product_ids") or []) if str(p).strip()]
    project_ids = [p for p in (zentao_cfg.get("project_ids") or []) if str(p).strip()]

    all_entries: list[dict[str, Any]] = []
    stats = {"bugs": 0, "stories": 0, "tasks": 0, "products": 0, "projects": 0, "executions": 0}

    with httpx.Client(timeout=30.0) as http:
        if not product_ids:
            products = _list_products(http, base, token)
            product_ids = [p.get("id") for p in products if p.get("id") is not None]
            stats["products"] = len(product_ids)
        if not project_ids:
            projects = _list_projects(http, base, token)
            project_ids = [p.get("id") for p in projects if p.get("id") is not None]
            stats["projects"] = len(project_ids)

        for pid in product_ids:
            bug_entries = _fetch_bugs_for_product(
                http, base, token, pid, date_str=date_str, account=account, only_my=only_my
            )
            stats["bugs"] += len(bug_entries)
            all_entries.extend(bug_entries)

        execution_count = 0
        for proj_id in project_ids:
            story_entries = _fetch_stories_for_project(
                http, base, token, proj_id, date_str=date_str, account=account, only_my=only_my
            )
            stats["stories"] += len(story_entries)
            all_entries.extend(story_entries)

            executions = _list_executions(http, base, token, proj_id)
            for exe in executions[:MAX_AUTO_EXECUTIONS]:
                exe_id = exe.get("id")
                if exe_id is None:
                    continue
                execution_count += 1
                task_entries = _fetch_tasks_for_execution(
                    http, base, token, exe_id, date_str=date_str, account=account, only_my=only_my
                )
                stats["tasks"] += len(task_entries)
                all_entries.extend(task_entries)
        stats["executions"] = execution_count

    entries = _dedupe_entries(all_entries)
    return {
        "entries": entries,
        "stats": stats,
        "account": account,
        "only_my_activity": only_my,
        "auto_discover": not (zentao_cfg.get("product_ids") or zentao_cfg.get("project_ids")),
    }


def ensure_token(zentao_cfg: dict[str, Any]) -> tuple[str, str, str]:
    """返回 (token, account, base_url)。"""
    base_url = normalize_base_url(zentao_cfg.get("base_url") or "")
    if not base_url:
        raise ZenTaoApiError("请在 config.yaml 配置 zentao.base_url")

    cache_path = resolve_token_cache_path(zentao_cfg)
    cached = load_token_cache(cache_path)
    if cached:
        token = str(cached.get("token") or "").strip()
        account = str(cached.get("account") or "").strip()
        cached_base = normalize_base_url(str(cached.get("base_url") or base_url))
        if token:
            return token, account, cached_base or base_url

    raise ZenTaoApiError(
        "未找到禅道登录凭证",
        code=AUTH_REQUIRED,
    )


def auth_status(zentao_cfg: dict[str, Any]) -> str:
    """返回 ok | auth_required | misconfigured。"""
    base_url = normalize_base_url(zentao_cfg.get("base_url") or "")
    if not base_url:
        return "misconfigured"
    cache_path = resolve_token_cache_path(zentao_cfg)
    if not load_token_cache(cache_path):
        return AUTH_REQUIRED
    try:
        ensure_token(zentao_cfg)
        return "ok"
    except ZenTaoApiError as exc:
        if exc.code in (AUTH_REQUIRED, TOKEN_EXPIRED):
            return exc.code
        return "error"

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

DEFAULT_TOKEN_CACHE = "data/.jira_token.json"
MAX_RESULTS = 100
MAX_PAGES = 20
SEARCH_FIELDS = "summary,issuetype,status,assignee,reporter,updated,created,resolutiondate"

ISSUE_TYPE_MAP = {
    "bug": "bug",
    "缺陷": "bug",
    "story": "story",
    "用户故事": "story",
    "需求": "story",
    "epic": "story",
    "task": "task",
    "任务": "task",
    "sub-task": "task",
    "子任务": "task",
    "subtask": "task",
}


class JiraApiError(RuntimeError):
    def __init__(self, message: str, *, code: str = "") -> None:
        super().__init__(message)
        self.code = code


AUTH_REQUIRED = "auth_required"
AUTH_FAILED = "auth_failed"


def normalize_base_url(base_url: str) -> str:
    return (base_url or "").strip().rstrip("/")


def resolve_token_cache_path(jira_cfg: dict[str, Any]) -> Path:
    from utils.paths import project_root

    raw = (jira_cfg.get("token_cache") or DEFAULT_TOKEN_CACHE).strip()
    path = Path(raw)
    if not path.is_absolute():
        path = project_root() / path
    return path


def load_token_cache(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if isinstance(data, dict) and (data.get("api_token") or data.get("token") or "").strip():
        return data
    return None


def save_token_cache(
    path: Path,
    *,
    api_token: str,
    username: str,
    base_url: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "api_token": api_token.strip(),
                "username": username.strip(),
                "base_url": normalize_base_url(base_url),
                "deployment": "server",
                "obtained_at": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def resolve_credentials(jira_cfg: dict[str, Any]) -> tuple[str, str, str]:
    """返回 (username, api_token, base_url)。"""
    base_url = normalize_base_url(jira_cfg.get("base_url") or "")
    if not base_url:
        raise JiraApiError("请在 config.yaml 配置 jira.base_url", code=AUTH_REQUIRED)

    cache = load_token_cache(resolve_token_cache_path(jira_cfg)) or {}
    username = (
        (jira_cfg.get("username") or jira_cfg.get("email") or cache.get("username") or "")
        .strip()
    )
    api_token = (
        (jira_cfg.get("api_token") or jira_cfg.get("token") or cache.get("api_token") or cache.get("token") or "")
        .strip()
    )
    cached_base = normalize_base_url(str(cache.get("base_url") or base_url))
    if not api_token:
        raise JiraApiError("未找到 Jira API Token（PAT）", code=AUTH_REQUIRED)
    return username, api_token, cached_base or base_url


def auth_status(jira_cfg: dict[str, Any]) -> str:
    if not jira_cfg.get("enabled"):
        return "disabled"
    if not normalize_base_url(jira_cfg.get("base_url") or ""):
        return "misconfigured"
    try:
        resolve_credentials(jira_cfg)
        return "ok"
    except JiraApiError as exc:
        return exc.code or "error"


def _auth_headers(username: str, api_token: str) -> dict[str, str]:
    """私有化 Jira：优先 Bearer PAT；无 username 时仍用 Bearer。"""
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if username:
        # 部分 Server 环境 PAT 仍走 Basic(username:token)
        token_bytes = f"{username}:{api_token}".encode("utf-8")
        headers["Authorization"] = f"Basic {base64.b64encode(token_bytes).decode('ascii')}"
    else:
        headers["Authorization"] = f"Bearer {api_token}"
    return headers


def _date_part(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "T" in text:
        return text.split("T", 1)[0]
    return text[:10]


def _time_part(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "12:00:00"
    if "T" in text:
        segment = text.split("T", 1)[1]
        for sep in ("+", "-"):
            if sep in segment:
                segment = segment.split(sep, 1)[0]
                break
        segment = segment.replace("Z", "")
        if "." in segment:
            segment = segment.split(".", 1)[0]
        if len(segment) >= 8:
            return segment[:8]
    return "12:00:00"


def _map_issue_type(name: str) -> str:
    lowered = (name or "").strip().lower()
    return ISSUE_TYPE_MAP.get(lowered, ISSUE_TYPE_MAP.get(name or "", "issue"))


def _pick_action_on_day(fields: dict[str, Any], date_str: str) -> tuple[str, str] | None:
    checks: list[tuple[str, str]] = [
        ("opened", "created"),
        ("resolved", "resolutiondate"),
        ("updated", "updated"),
    ]
    for action, field in checks:
        raw = fields.get(field)
        if _date_part(raw) == date_str:
            return action, str(raw or "")
    return None


def _action_label(action: str, issue_type: str) -> str:
    labels = {"opened": "新建", "resolved": "解决", "updated": "更新"}
    type_labels = {"bug": "Bug", "story": "Story", "task": "Task", "issue": "Issue"}
    return f"{labels.get(action, action)}{type_labels.get(issue_type, 'Issue')}"


def _issue_url(base_url: str, key: str) -> str:
    return f"{normalize_base_url(base_url)}/browse/{key}"


def _build_jql(date_str: str, jira_cfg: dict[str, Any]) -> str:
    next_day = (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    clauses: list[str] = []

    if jira_cfg.get("only_my_activity", True):
        clauses.append("(assignee = currentUser() OR reporter = currentUser())")

    clauses.append(f'updated >= "{date_str} 00:00"')
    clauses.append(f'updated < "{next_day} 00:00"')

    project_keys = [str(k).strip() for k in (jira_cfg.get("project_keys") or []) if str(k).strip()]
    if project_keys:
        quoted = ", ".join(f'"{k}"' for k in project_keys)
        clauses.append(f"project in ({quoted})")

    extra = (jira_cfg.get("jql_extra") or "").strip()
    if extra:
        clauses.append(f"({extra})")

    return " AND ".join(clauses) + " ORDER BY updated ASC"


def _search_issues(
    http: httpx.Client,
    base_url: str,
    headers: dict[str, str],
    jql: str,
) -> list[dict[str, Any]]:
    url = f"{normalize_base_url(base_url)}/rest/api/2/search"
    issues: list[dict[str, Any]] = []
    start_at = 0

    for _ in range(MAX_PAGES):
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": MAX_RESULTS,
            "fields": SEARCH_FIELDS,
        }
        resp = http.get(url, headers=headers, params=params)
        if resp.status_code in (401, 403):
            raise JiraApiError(
                f"认证失败 HTTP {resp.status_code}，请检查 PAT 与用户名",
                code=AUTH_FAILED,
            )
        if resp.status_code >= 400:
            raise JiraApiError(f"Jira 搜索失败 HTTP {resp.status_code}: {resp.text[:300]}")

        payload = resp.json()
        batch = payload.get("issues") or []
        if isinstance(batch, list):
            issues.extend(i for i in batch if isinstance(i, dict))

        total = int(payload.get("total") or 0)
        start_at += len(batch)
        if start_at >= total or not batch:
            break

    return issues


def _issues_to_entries(
    issues: list[dict[str, Any]],
    *,
    date_str: str,
    base_url: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for issue in issues:
        key = issue.get("key") or ""
        fields = issue.get("fields") or {}
        if not isinstance(fields, dict):
            continue
        picked = _pick_action_on_day(fields, date_str)
        if not picked:
            continue
        action, when = picked
        issuetype = fields.get("issuetype") or {}
        type_name = issuetype.get("name") if isinstance(issuetype, dict) else str(issuetype or "")
        mapped_type = _map_issue_type(type_name)
        summary = (fields.get("summary") or key).strip()
        status = fields.get("status") or {}
        status_name = status.get("name") if isinstance(status, dict) else str(status or "")

        prefix = _action_label(action, mapped_type)
        detail_parts = [f"type: {type_name or mapped_type}"]
        if status_name:
            detail_parts.append(f"status: {status_name}")

        entries.append(
            {
                "id": f"jira-{key}-{action}-{date_str}",
                "time": _time_part(when),
                "title": f"{prefix} {key} {summary}".strip(),
                "detail": " | ".join(detail_parts),
                "url": _issue_url(base_url, key),
                "object_type": mapped_type,
                "issue_key": key,
                "action": action,
                "raw": {
                    "key": key,
                    "summary": summary,
                    "issuetype": type_name,
                    "status": status_name,
                    "action": action,
                },
            }
        )

    entries.sort(key=lambda e: (e.get("time") or "", e.get("id") or ""))
    return entries


def fetch_entries_for_day(
    jira_cfg: dict[str, Any],
    *,
    date_str: str,
) -> dict[str, Any]:
    username, api_token, base_url = resolve_credentials(jira_cfg)
    jql = _build_jql(date_str, jira_cfg)
    headers = _auth_headers(username, api_token)

    with httpx.Client(timeout=30.0, verify=True) as http:
        issues = _search_issues(http, base_url, headers, jql)

    entries = _issues_to_entries(issues, date_str=date_str, base_url=base_url)
    stats = {
        "total": len(entries),
        "bug": sum(1 for e in entries if e.get("object_type") == "bug"),
        "story": sum(1 for e in entries if e.get("object_type") == "story"),
        "task": sum(1 for e in entries if e.get("object_type") == "task"),
        "issue": sum(1 for e in entries if e.get("object_type") == "issue"),
    }
    return {
        "entries": entries,
        "stats": stats,
        "jql": jql,
        "username": username,
        "deployment": "server",
        "only_my_activity": bool(jira_cfg.get("only_my_activity", True)),
    }

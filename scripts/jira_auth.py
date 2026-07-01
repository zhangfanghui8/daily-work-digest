from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collectors.pms.jira_client import (
    AUTH_REQUIRED,
    JiraApiError,
    auth_status,
    normalize_base_url,
    resolve_credentials,
    resolve_token_cache_path,
    save_token_cache,
)
from utils.config_loader import load_config
from utils.paths import project_root


def _jira_cfg(config: dict) -> dict:
    return config.get("jira") or {}


def cmd_paste_token(
    token_cache: Path,
    api_token: str,
    username: str,
    base_url: str,
) -> None:
    api_token = api_token.strip()
    if not api_token:
        raise SystemExit("api_token 不能为空")
    if not base_url.strip():
        raise SystemExit("请提供 --base-url 或在 config.yaml 配置 jira.base_url")
    save_token_cache(
        token_cache,
        api_token=api_token,
        username=username.strip(),
        base_url=normalize_base_url(base_url),
    )
    rel = token_cache.relative_to(project_root())
    print("JIRA_AUTH_OK")
    print(f"已写入 token 缓存: {rel}")


def cmd_check(config: dict, token_cache: Path) -> None:
    jira = _jira_cfg(config)
    status = auth_status(jira)
    payload = {
        "enabled": bool(jira.get("enabled")),
        "base_url": normalize_base_url(jira.get("base_url") or ""),
        "status": status,
        "token_cache": str(token_cache.relative_to(project_root())),
        "deployment": "server",
    }
    print(json.dumps(payload, ensure_ascii=False))
    if status == AUTH_REQUIRED:
        sys.exit(2)


def cmd_status(config: dict, token_cache: Path) -> None:
    jira = _jira_cfg(config)
    print(f"deployment: server (私有化)")
    print(f"base_url: {normalize_base_url(jira.get('base_url') or '') or '(未配置)'}")
    print(f"status: {auth_status(jira)}")
    if token_cache.is_file():
        print(f"token_cache: {token_cache.relative_to(project_root())}")
    try:
        username, _, base = resolve_credentials(jira)
        print(f"username: {username or '(Bearer PAT)'}")
        print(f"resolved_base: {base}")
    except JiraApiError as exc:
        print(f"凭证: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Jira 私有化 PAT 配置（Agent 代写 token 缓存）")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--token-cache", type=Path, default=None)
    parser.add_argument("--paste-token", metavar="PAT", help="粘贴 Personal Access Token")
    parser.add_argument("--username", default="", help="Jira 登录名（建议填写）")
    parser.add_argument("--base-url", default="", help="Jira 站点 URL")
    parser.add_argument("--check", action="store_true", help="JSON 输出凭证状态")
    parser.add_argument("--status", action="store_true", help="查看配置状态")
    args = parser.parse_args()

    config = load_config(args.config)
    jira = _jira_cfg(config)
    token_cache = args.token_cache or resolve_token_cache_path(jira)

    if args.paste_token:
        base_url = args.base_url or normalize_base_url(jira.get("base_url") or "")
        cmd_paste_token(token_cache, args.paste_token, args.username, base_url)
    elif args.check:
        cmd_check(config, token_cache)
    elif args.status:
        cmd_status(config, token_cache)
    else:
        parser.print_help()
        print("\n推荐: python scripts/jira_auth.py --paste-token PAT --username 登录名")


if __name__ == "__main__":
    main()

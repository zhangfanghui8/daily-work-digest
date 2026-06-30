from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collectors.docs.yuque_client import (
    YuqueOpenApiError,
    _api_base,
    get_current_user,
    list_user_repos,
    normalize_repos,
    resolve_auth,
    resolve_auth_mode,
)
from utils.config_loader import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="语雀文档配置调试")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--whoami", action="store_true", help="显示当前认证对应用户")
    parser.add_argument("--list-repos", action="store_true", help="列出当前用户可访问的知识库")
    args = parser.parse_args()

    cfg = load_config(args.config)
    docs = (cfg.get("yuque") or {}).get("docs") or {}

    try:
        auth = resolve_auth(docs)
    except YuqueOpenApiError as exc:
        raise SystemExit(str(exc)) from exc

    api_base = _api_base(docs)
    auth_mode = resolve_auth_mode(docs)
    print(f"auth_mode: {auth_mode}")

    if args.whoami or args.list_repos:
        try:
            user = get_current_user(auth, api_base=api_base)
        except YuqueOpenApiError as exc:
            label = "Cookie" if auth.is_cookie else "Token"
            raise SystemExit(f"{label} 无效: {exc}") from exc

        if args.whoami:
            print(f"login: {user.get('login')}")
            print(f"id: {user.get('id')}")
            print(f"name: {user.get('name')}")

        if args.list_repos:
            login = (user.get("login") or "").strip()
            if not login:
                raise SystemExit("无法获取用户 login")
            repos = list_user_repos(login, auth, api_base=api_base)
            print(f"共 {len(repos)} 个知识库（首页）：")
            for repo in repos:
                if not isinstance(repo, dict):
                    continue
                book_id = repo.get("id")
                slug = repo.get("slug") or ""
                name = repo.get("name") or ""
                user_obj = repo.get("user") or {}
                group_login = user_obj.get("login") if isinstance(user_obj, dict) else ""
                if group_login and slug:
                    ns = f"{group_login}/{slug}"
                else:
                    ns = str(book_id)
                print(f"  namespace={ns}  name={name}  id={book_id}")
    else:
        configured = normalize_repos(docs.get("repos"))
        auto = docs.get("auto_repos", True)
        print("已配置 repos:", configured or f"（空，将自动发现，auto_repos={auto}）")
        print("\n用法:")
        print("  python scripts/debug_yuque_docs.py --whoami")
        print("  python scripts/debug_yuque_docs.py --list-repos")


if __name__ == "__main__":
    main()

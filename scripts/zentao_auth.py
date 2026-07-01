from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collectors.pms.zentao_client import (
    AUTH_REQUIRED,
    ZenTaoApiError,
    auth_status,
    ensure_token,
    load_token_cache,
    login,
    normalize_base_url,
    resolve_token_cache_path,
    save_token_cache,
)
from utils.config_loader import load_config
from utils.paths import project_root


def _zentao_cfg(config: dict) -> dict:
    return config.get("zentao") or {}


def cmd_login(
    config: dict,
    token_cache: Path,
    *,
    account: str = "",
    password: str = "",
) -> None:
    zentao = _zentao_cfg(config)
    base_url = normalize_base_url(zentao.get("base_url") or "")
    if not base_url:
        raise SystemExit("请在 config.yaml 配置 zentao.base_url")

    account = (account or zentao.get("account") or "").strip()
    if not account:
        account = input("禅道账号: ").strip()
    if not password:
        password = os.environ.get("ZENTAO_PASSWORD") or ""
    if not password:
        password = getpass.getpass("禅道密码: ")
    if not account or not password:
        raise SystemExit("账号或密码不能为空")

    try:
        token = login(base_url, account, password)
    except ZenTaoApiError as exc:
        raise SystemExit(f"登录失败: {exc}") from exc

    save_token_cache(token_cache, token=token, account=account, base_url=base_url)
    rel = token_cache.relative_to(project_root())
    print(f"\nZENTAO_AUTH_OK")
    print(f"已写入登录缓存: {rel}")


def cmd_paste_token(token_cache: Path, token: str, account: str, base_url: str) -> None:
    token = token.strip()
    if not token:
        raise SystemExit("token 不能为空")
    if not base_url.strip():
        raise SystemExit("请提供 --base-url 或在 config.yaml 配置 zentao.base_url")
    account = account.strip() or "unknown"
    save_token_cache(
        token_cache,
        token=token,
        account=account,
        base_url=normalize_base_url(base_url),
    )
    rel = token_cache.relative_to(project_root())
    print(f"ZENTAO_AUTH_OK")
    print(f"已写入 token 缓存: {rel}")


def cmd_status(config: dict, token_cache: Path, *, json_out: bool = False) -> None:
    zentao = _zentao_cfg(config)
    base_url = normalize_base_url(zentao.get("base_url") or "")
    status = auth_status(zentao) if zentao.get("enabled") else "disabled"
    cached = load_token_cache(token_cache)

    if json_out:
        payload = {
            "enabled": bool(zentao.get("enabled")),
            "base_url": base_url,
            "status": status,
            "account": (cached or {}).get("account") if cached else None,
            "token_cache": str(token_cache.relative_to(project_root())),
        }
        print(json.dumps(payload, ensure_ascii=False))
        return

    print(f"base_url: {base_url or '(未配置)'}")
    print(f"status: {status}")
    if not cached:
        print("token 缓存: 无")
        return
    print(f"token 缓存: {token_cache.relative_to(project_root())}")
    print(f"  account: {cached.get('account')}")
    print(f"  obtained_at: {cached.get('obtained_at')}")
    if status == "ok":
        try:
            _, account, resolved_base = ensure_token(zentao)
            print(f"  token 有效（account={account}, base={resolved_base}）")
        except ZenTaoApiError as exc:
            print(f"  token 不可用: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="禅道登录（Agent 代跑 --login；密码不进 config.yaml）",
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--token-cache",
        type=Path,
        default=None,
        help="token 缓存路径；默认 data/.zentao_token.json",
    )
    parser.add_argument("--login", action="store_true", help="登录并缓存 token")
    parser.add_argument("--account", default="", help="禅道账号（可选，未填则交互输入）")
    parser.add_argument(
        "--password",
        default="",
        help="禅道密码（可选；优先用环境变量 ZENTAO_PASSWORD，Agent 代登录时用）",
    )
    parser.add_argument("--paste-token", metavar="TOKEN", help="粘贴 API 调试台 token（高级）")
    parser.add_argument("--base-url", default="", help="与 --paste-token 配合")
    parser.add_argument("--status", action="store_true", help="查看登录状态")
    parser.add_argument("--check", action="store_true", help="JSON 输出状态（供 Agent 检测）")
    args = parser.parse_args()

    config = load_config(args.config)
    zentao = _zentao_cfg(config)
    token_cache = args.token_cache or resolve_token_cache_path(zentao)

    if args.login:
        cmd_login(config, token_cache, account=args.account, password=args.password)
    elif args.paste_token:
        base_url = args.base_url or normalize_base_url(zentao.get("base_url") or "")
        cmd_paste_token(token_cache, args.paste_token, args.account, base_url)
    elif args.check:
        cmd_status(config, token_cache, json_out=True)
        status = auth_status(zentao) if zentao.get("enabled") else "disabled"
        if status == AUTH_REQUIRED:
            sys.exit(2)
        if status not in ("ok", "disabled", "misconfigured"):
            sys.exit(1)
    elif args.status:
        cmd_status(config, token_cache)
    else:
        parser.print_help()
        print("\nAgent 代登录: python scripts/zentao_auth.py --login --account 你的账号")
        print("（密码通过 ZENTAO_PASSWORD 环境变量传入，或终端 getpass 输入）")


if __name__ == "__main__":
    main()

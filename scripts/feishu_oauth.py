from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collectors.docs.feishu_client import (
    DEFAULT_BASE_URL,
    exchange_code_for_tokens,
    oauth_authorize_url,
    oauth_scope,
    resolve_token_cache_path,
)
from utils.config_loader import load_config
from utils.paths import project_root

_SUCCESS_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>授权成功</title></head>
<body style="font-family:sans-serif;text-align:center;padding:48px">
<h2>飞书授权成功</h2>
<p>可以关闭此页面，回到 Cursor / 终端继续。</p>
</body></html>"""

_ERROR_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>授权失败</title></head>
<body style="font-family:sans-serif;text-align:center;padding:48px">
<h2>飞书授权未完成</h2>
<p>请关闭此页面，回到终端查看提示后重试。</p>
</body></html>"""


def _docs_cfg(config: dict) -> dict:
    feishu = config.get("feishu") or {}
    return feishu.get("docs") or {}


def _resolve_credentials(config: dict) -> tuple[str, str, str]:
    feishu = config.get("feishu") or {}
    docs = _docs_cfg(config)
    chat = feishu.get("chat") or {}
    app_id = (docs.get("app_id") or chat.get("app_id") or "").strip()
    app_secret = (docs.get("app_secret") or chat.get("app_secret") or "").strip()
    base_url = (docs.get("base_url") or DEFAULT_BASE_URL).strip()
    if not app_id or not app_secret:
        raise SystemExit("请在 config.yaml 配置 feishu.docs.app_id / app_secret（或复用 feishu.chat）")
    return app_id, app_secret, base_url


def _default_redirect_uri(config: dict) -> str:
    docs = _docs_cfg(config)
    return (docs.get("redirect_uri") or "http://127.0.0.1:8765/callback").strip()


def _save_oauth_tokens(token_cache: Path, data: dict) -> None:
    access_token = data.get("access_token") or ""
    refresh_token = data.get("refresh_token") or ""
    if not access_token:
        raise SystemExit("OAuth 响应缺少 access_token")

    token_cache.parent.mkdir(parents=True, exist_ok=True)
    token_cache.write_text(
        json.dumps(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": data.get("expires_in"),
                "refresh_token_expires_in": data.get("refresh_token_expires_in"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    rel = token_cache.relative_to(project_root())
    print(f"已写入 token 缓存: {rel}")
    if refresh_token:
        print("已获取 refresh_token，后续采集可自动刷新。")
    else:
        print("未获取 refresh_token（约 2 小时有效）。若需长期自动续期，请开通 offline_access 后重试 --login。")


def _exchange_and_save(
    config: dict,
    code: str,
    redirect_uri: str,
    token_cache: Path,
) -> None:
    app_id, app_secret, base_url = _resolve_credentials(config)
    data = exchange_code_for_tokens(
        app_id, app_secret, code, redirect_uri, base_url=base_url
    )
    _save_oauth_tokens(token_cache, data)


class _OAuthCallbackState:
    code: str | None = None
    error: str | None = None
    event = threading.Event()


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    callback_path = "/callback"
    state = _OAuthCallbackState

    def log_message(self, format: str, *args) -> None:
        _ = format, args

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != self.callback_path:
            self.send_error(404)
            return

        params = parse_qs(parsed.query)
        OAuthCallbackHandler.state.code = (params.get("code") or [None])[0]
        OAuthCallbackHandler.state.error = (params.get("error") or [None])[0]
        OAuthCallbackHandler.state.event.set()

        body = _SUCCESS_HTML if OAuthCallbackHandler.state.code else _ERROR_HTML
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def cmd_login(
    config: dict,
    redirect_uri: str,
    token_cache: Path,
    *,
    use_offline: bool = True,
    timeout_sec: int = 180,
) -> None:
    """一键登录：本地监听回调 + 自动打开浏览器，用户只需在飞书页点「同意」。"""
    app_id, _, base_url = _resolve_credentials(config)
    scope = oauth_scope(offline=use_offline)
    auth_url = oauth_authorize_url(
        app_id, redirect_uri, base_url=base_url, scope=scope
    )

    parsed = urlparse(redirect_uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8765
    OAuthCallbackHandler.callback_path = parsed.path or "/callback"
    OAuthCallbackHandler.state = _OAuthCallbackState()

    server = HTTPServer((host, port), OAuthCallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print("即将打开浏览器，请在飞书页面点击「授权 / 同意」…")
    print(f"（若未自动打开，请手动访问授权链接；本地监听 {host}:{port}）\n")
    try:
        webbrowser.open(auth_url)
    except Exception:
        print(auth_url)

    if not OAuthCallbackHandler.state.event.wait(timeout=timeout_sec):
        server.shutdown()
        raise SystemExit(f"授权超时（{timeout_sec}s）。请重试: python scripts/feishu_oauth.py --login")

    server.shutdown()

    if OAuthCallbackHandler.state.error:
        raise SystemExit(f"飞书授权被拒绝或失败: {OAuthCallbackHandler.state.error}")
    if not OAuthCallbackHandler.state.code:
        raise SystemExit("未收到授权码，请重试: python scripts/feishu_oauth.py --login")

    _exchange_and_save(config, OAuthCallbackHandler.state.code, redirect_uri, token_cache)
    print("\n完成。可运行: python scripts/collect_all.py --date today --sources feishu_docs")


def cmd_authorize(config: dict, redirect_uri: str, *, use_offline: bool = True) -> None:
    app_id, _, base_url = _resolve_credentials(config)
    scope = oauth_scope(offline=use_offline)
    url = oauth_authorize_url(app_id, redirect_uri, base_url=base_url, scope=scope)
    cache_path = resolve_token_cache_path(_docs_cfg(config))
    print("请在浏览器打开以下链接完成飞书授权：\n")
    print(url)
    print(f"\n授权成功后 token 将写入: {cache_path.relative_to(project_root())}")
    print("推荐改用一键登录（无需复制 URL）:")
    print("  python scripts/feishu_oauth.py --login")


def cmd_exchange(config: dict, callback_url: str, redirect_uri: str, token_cache: Path) -> None:
    parsed = urlparse(callback_url.strip())
    params = parse_qs(parsed.query)
    code_list = params.get("code") or []
    if not code_list:
        raise SystemExit("回调 URL 中未找到 code 参数")
    _exchange_and_save(config, code_list[0], redirect_uri, token_cache)


def cmd_paste(
    token_cache: Path,
    access_token: str,
    refresh_token: str = "",
) -> None:
    access_token = access_token.strip()
    if not access_token:
        raise SystemExit("access_token 不能为空")
    refresh_token = refresh_token.strip()

    token_cache.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, str | int] = {"access_token": access_token}
    if refresh_token:
        payload["refresh_token"] = refresh_token
    token_cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    rel = token_cache.relative_to(project_root())
    print(f"已写入 token 缓存: {rel}")
    if refresh_token:
        print("含 refresh_token，后续采集可自动刷新。")
    else:
        print("注意: 仅 access_token（约 2 小时有效），过期后重新 --login 或 --paste-token。")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="飞书文档 OAuth 授权（推荐 --login，用户只需在浏览器点同意）",
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--redirect-uri",
        default=None,
        help="须与开放平台「安全设置 → 重定向 URL」一致；默认读 config",
    )
    parser.add_argument(
        "--token-cache",
        type=Path,
        default=None,
        help="token 缓存路径；默认读 config feishu.docs.token_cache",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="一键登录：自动打开浏览器并接收回调（推荐）",
    )
    parser.add_argument(
        "--no-offline",
        action="store_true",
        help="不申请 offline_access（遇 20027 权限不足时使用，token 约 2h 有效）",
    )
    parser.add_argument("--authorize", action="store_true", help="仅打印授权链接（高级）")
    parser.add_argument("--exchange", metavar="CALLBACK_URL", help="手动粘贴回调 URL（高级）")
    parser.add_argument(
        "--paste-token",
        metavar="ACCESS_TOKEN",
        help="粘贴调试台 token（高级）",
    )
    parser.add_argument("--refresh-token", default="", help="与 --paste-token 配合")
    args = parser.parse_args()

    config = load_config(args.config)
    docs = _docs_cfg(config)
    redirect_uri = args.redirect_uri or _default_redirect_uri(config)
    token_cache = (
        args.token_cache if args.token_cache is not None else resolve_token_cache_path(docs)
    )
    if not token_cache.is_absolute():
        token_cache = project_root() / token_cache
    use_offline = not args.no_offline

    if args.login:
        cmd_login(config, redirect_uri, token_cache, use_offline=use_offline)
    elif args.paste_token:
        cmd_paste(token_cache, args.paste_token, args.refresh_token)
    elif args.exchange:
        cmd_exchange(config, args.exchange, redirect_uri, token_cache)
    elif args.authorize:
        cmd_authorize(config, redirect_uri, use_offline=use_offline)
    else:
        parser.print_help()
        print("\n推荐: python scripts/feishu_oauth.py --login")


if __name__ == "__main__":
    main()

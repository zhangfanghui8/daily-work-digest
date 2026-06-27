from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx

from collectors.chat.feishu_client import DEFAULT_BASE_URL, get_tenant_access_token
from utils.config_loader import load_config


def _chat_cfg(config: dict) -> dict:
    feishu = config.get("feishu") or {}
    chat = feishu.get("chat") or {}
    app_id = (chat.get("app_id") or "").strip()
    app_secret = (chat.get("app_secret") or "").strip()
    base_url = (chat.get("base_url") or DEFAULT_BASE_URL).strip()
    if not app_id or not app_secret:
        raise SystemExit("请在 config.yaml 配置 feishu.chat.app_id 与 app_secret")
    return {"app_id": app_id, "app_secret": app_secret, "base_url": base_url}


def list_chats(token: str, base_url: str) -> None:
    url = f"{base_url.rstrip('/')}/open-apis/im/v1/chats"
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=headers, params={"page_size": 50})
        resp.raise_for_status()
        payload = resp.json()
    if payload.get("code") != 0:
        print(f"失败: code={payload.get('code')} msg={payload.get('msg')}")
        print("提示: 需 im:chat:readonly 权限")
        return
    items = (payload.get("data") or {}).get("items") or []
    print(f"共 {len(items)} 个群（首页，最多 50）：")
    for item in items:
        if not isinstance(item, dict):
            continue
        print(f"  chat_id={item.get('chat_id')}  name={item.get('name')}")


def whoami(token: str, base_url: str) -> None:
    url = f"{base_url.rstrip('/')}/open-apis/authen/v1/user_info"
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("提示: 若失败，请在开放平台用「获取单个用户信息」等接口查 open_id，或从消息 sender.id 获取")


def main() -> None:
    parser = argparse.ArgumentParser(description="飞书 IM 配置调试")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--list-chats", action="store_true", help="列出机器人可见群 chat_id")
    parser.add_argument("--whoami", action="store_true", help="尝试查询当前身份（需额外权限）")
    args = parser.parse_args()

    cfg = load_config(args.config)
    chat_cfg = _chat_cfg(cfg)
    token = get_tenant_access_token(
        chat_cfg["app_id"],
        chat_cfg["app_secret"],
        base_url=chat_cfg["base_url"],
    )
    print("tenant_access_token 获取成功")

    if args.list_chats:
        list_chats(token, chat_cfg["base_url"])
    elif args.whoami:
        whoami(token, chat_cfg["base_url"])
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

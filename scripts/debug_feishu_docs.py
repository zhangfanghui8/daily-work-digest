"""诊断飞书文档搜索 API（不写 token 到输出）。"""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx

from collectors.docs.feishu_client import resolve_user_access_token, search_my_edited_docs
from utils.config_loader import load_config
from utils.date_utils import day_bounds, resolve_date
from utils.paths import project_root


def _summarize_units(units: list) -> list[dict]:
    out = []
    for u in units[:20]:
        if not isinstance(u, dict):
            continue
        meta = u.get("result_meta") or {}
        out.append(
            {
                "title": (u.get("title_highlighted") or "")[:80],
                "entity_type": u.get("entity_type"),
                "doc_type": meta.get("doc_types") or meta.get("file_type"),
                "update_time": meta.get("update_time"),
                "url": meta.get("url"),
            }
        )
    return out


def main() -> None:
    cfg = load_config()
    tz = cfg.get("timezone", "Asia/Shanghai")
    date_str = resolve_date("today", tz).isoformat()
    feishu = cfg.get("feishu") or {}
    docs = feishu.get("docs") or {}

    start_dt, end_dt = day_bounds(date_str, tz)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp()) - 1

    report: dict = {
        "date": date_str,
        "timezone": tz,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "start_human": start_dt.isoformat(),
        "end_human": end_dt.isoformat(),
        "tests": {},
    }

    with httpx.Client(timeout=30.0) as client:
        token = resolve_user_access_token(docs, feishu, client=client)

        cases = {
            "today_with_types": {
                "start_ts": start_ts,
                "end_ts": end_ts,
                "doc_types": ["DOC", "DOCX", "SHEET", "BITABLE", "WIKI", "MINDNOTE", "SLIDES"],
            },
            "today_no_types": {"start_ts": start_ts, "end_ts": end_ts, "doc_types": None},
            "last_7_days_no_types": {
                "start_ts": start_ts - 7 * 86400,
                "end_ts": end_ts,
                "doc_types": None,
            },
        }

        for name, opts in cases.items():
            units = search_my_edited_docs(
                token,
                start_ts=opts["start_ts"],
                end_ts=opts["end_ts"],
                doc_types=opts.get("doc_types"),
                client=client,
            )
            report["tests"][name] = {
                "count": len(units),
                "samples": _summarize_units(units),
            }

    out = project_root() / "data" / "_debug_feishu_search.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written: {out.relative_to(project_root())}")
    for name, t in report["tests"].items():
        print(f"  {name}: {t['count']}")


if __name__ == "__main__":
    main()

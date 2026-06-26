from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collectors import run_collectors
from processors.merge import merge_daily, merge_week
from utils.config_loader import load_config
from utils.date_utils import resolve_date


def collect_and_merge(
    date_str: str,
    config_path: Path | None = None,
    sources: list[str] | None = None,
    week: bool = False,
) -> None:
    print(f"=== L1 采集 {date_str} ===")
    run_collectors(date_str, config_path, sources)

    print(f"\n=== L2 归并 {date_str} ===")
    merge_daily(date_str, config_path)

    if week:
        print(f"\n=== L2 周报归并 ===")
        merge_week(date_str, config_path)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="L1 采集层对外入口：运行各渠道 Adapter 并归并 digest",
    )
    parser.add_argument("--date", default="today", help="today / yesterday / YYYY-MM-DD")
    parser.add_argument(
        "--sources",
        default="all",
        help="采集渠道，逗号分隔：git,manual,wecom,feishu,dingtalk,all（默认 all）",
    )
    parser.add_argument("--week", action="store_true", help="采集后额外生成本周周报 digest")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="仅 L1 采集，不归并",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    timezone = cfg.get("timezone", "Asia/Shanghai")
    date_str = resolve_date(args.date, timezone).isoformat()

    sources = None if args.sources.strip().lower() == "all" else [
        s.strip().lower() for s in args.sources.split(",") if s.strip()
    ]

    if args.collect_only:
        print(f"=== L1 采集 {date_str} ===")
        run_collectors(date_str, args.config, sources)
        return

    collect_and_merge(date_str, args.config, sources, week=args.week)
    print("\n完成。可让 AI 助手按 SKILL.md 生成日报（如：「生成今天的工作日报」）")


if __name__ == "__main__":
    main()

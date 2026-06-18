"""L2 规则层对外入口。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from processors.merge import merge_daily, merge_week
from utils.config_loader import load_config
from utils.date_utils import resolve_date


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="L2 归并 raw 数据，生成 digest JSON")
    parser.add_argument("--date", default="today", help="today / yesterday / YYYY-MM-DD")
    parser.add_argument("--week", action="store_true", help="合并本周 daily digest 为周报数据")
    parser.add_argument("--config", type=Path, default=None)
    args = parser.parse_args()

    cfg = load_config(args.config)
    timezone = cfg.get("timezone", "Asia/Shanghai")

    if args.week:
        merge_week(args.date, args.config)
        return

    date_str = resolve_date(args.date, timezone).isoformat()
    merge_daily(date_str, args.config)


if __name__ == "__main__":
    main()

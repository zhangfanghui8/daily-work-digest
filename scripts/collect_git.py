"""L1 采集层 CLI 兼容入口，等价于 collect_all.py --collect-only --sources git。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collect_all import main

if __name__ == "__main__":
    if "--collect-only" not in sys.argv and "--sources" not in sys.argv:
        sys.argv.extend(["--collect-only", "--sources", "git"])
    main()

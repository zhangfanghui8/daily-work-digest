from __future__ import annotations

import re
from pathlib import Path
from typing import Any, ClassVar

from utils.paths import manual_path

from .base import BaseCollector

MANUAL_LINE = re.compile(r"^-\s*(?:(\d{1,2}:\d{2})\s+)?(.+)$")


class ManualCollector(BaseCollector):
    source: ClassVar[str] = "manual"
    output_filename: ClassVar[str] = "manual.json"

    @classmethod
    def source_name(cls) -> str:
        return cls.source

    @classmethod
    def is_enabled(cls, config: dict[str, Any]) -> bool:
        return config.get("manual", {}).get("enabled", True)

    def collect(self, date_str: str) -> dict[str, Any]:
        md_path = manual_path(date_str)
        entries = self._parse_markdown(md_path)

        if md_path.is_file():
            print(f"  └─ {md_path.name}: {len(entries)} 条补记")
        else:
            print("  └─ 无补记文件（可创建 data/manual/{date}.md）")

        return {
            "date": date_str,
            "timezone": self.timezone,
            "source": self.source,
            "markdown_path": str(md_path) if md_path.is_file() else "",
            "entries": entries,
        }

    def _parse_markdown(self, path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []

        entries: list[dict[str, Any]] = []
        for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = MANUAL_LINE.match(line)
            if not match:
                continue
            time_part, title = match.groups()
            time_value = (
                f"{time_part}:00"
                if time_part and len(time_part) == 5
                else (time_part or "12:00:00")
            )
            entries.append(
                {
                    "id": f"manual-{idx:03d}",
                    "time": time_value,
                    "title": title.strip(),
                    "line": line,
                }
            )
        return entries

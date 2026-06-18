from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from utils.paths import ensure_data_dirs, project_root, raw_dir


class BaseCollector(ABC):
    """L1 采集 Adapter 基类：各渠道继承并实现 collect()。"""

    source: ClassVar[str]
    output_filename: ClassVar[str]

    def __init__(self, config: dict[str, Any], config_path: Path | None = None) -> None:
        self.config = config
        self.config_path = config_path
        self.timezone = config.get("timezone", "Asia/Shanghai")

    @classmethod
    @abstractmethod
    def source_name(cls) -> str:
        """渠道标识，如 git / manual / chat。"""

    @classmethod
    def is_enabled(cls, config: dict[str, Any]) -> bool:
        """是否启用该采集器，子类可覆盖。"""
        return True

    @abstractmethod
    def collect(self, date_str: str) -> dict[str, Any]:
        """采集指定日期的原始数据，返回可 JSON 序列化的 dict。"""

    def output_path(self, date_str: str) -> Path:
        return raw_dir(date_str) / self.output_filename

    def run(self, date_str: str) -> Path:
        ensure_data_dirs(date_str)
        payload = self.collect(date_str)
        out_path = self.output_path(date_str)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.log_result(date_str, payload)
        rel = out_path.relative_to(project_root())
        print(f"[{self.source_name()}] 已写入: {rel}")
        return out_path

    def log_result(self, date_str: str, payload: dict[str, Any]) -> None:
        """子类可覆盖，打印采集摘要。"""
        _ = date_str

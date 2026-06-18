from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    """Repository root (parent of scripts/)."""
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return project_root() / "data"


def raw_dir(date_str: str) -> Path:
    return data_dir() / "raw" / date_str


def digest_dir() -> Path:
    return data_dir() / "digest"


def manual_dir() -> Path:
    return data_dir() / "manual"


def digest_path(date_str: str) -> Path:
    return digest_dir() / f"{date_str}.json"


def manual_path(date_str: str) -> Path:
    return manual_dir() / f"{date_str}.md"


def ensure_data_dirs(date_str: str) -> None:
    raw_dir(date_str).mkdir(parents=True, exist_ok=True)
    digest_dir().mkdir(parents=True, exist_ok=True)
    manual_dir().mkdir(parents=True, exist_ok=True)

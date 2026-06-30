from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from utils.date_utils import day_bounds

from .base import BaseCollector


def _run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise RuntimeError(f"git 命令失败 ({repo}): {stderr or result.stdout}")
    return result.stdout


def _should_exclude(message: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if re.search(pattern, message, flags=re.IGNORECASE):
            return True
    return False


def _branch_from_decorated_refs(refs: str) -> str:
    """从 git log %D 装饰信息提取分支名（优先本地分支）。"""
    refs = (refs or "").strip()
    if not refs:
        return ""
    local: list[str] = []
    remote: list[str] = []
    for segment in refs.split(","):
        segment = segment.strip()
        if "->" in segment:
            segment = segment.split("->", 1)[1].strip()
        if not segment or segment == "HEAD":
            continue
        if segment.startswith("tag:"):
            continue
        if segment.startswith("origin/"):
            remote.append(segment.removeprefix("origin/"))
        else:
            local.append(segment)
    if local:
        return local[0]
    if remote:
        return remote[0]
    return ""


def _parse_log_output(text: str) -> list[dict[str, Any]]:
    commits: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    files_changed = 0
    insertions = 0
    deletions = 0

    for line in text.splitlines():
        if line.startswith("COMMIT|"):
            if current is not None:
                current["files_changed"] = files_changed
                current["insertions"] = insertions
                current["deletions"] = deletions
                commits.append(current)
            parts = line.split("|", 6)
            if len(parts) < 7:
                continue
            _, commit_hash, authored, author_name, author_email, refs, message = parts
            current = {
                "hash": commit_hash,
                "authored_at": authored.strip(),
                "author_name": author_name.strip(),
                "author_email": author_email.strip(),
                "refs": refs.strip(),
                "message": message.strip(),
                "files_changed": 0,
                "insertions": 0,
                "deletions": 0,
            }
            files_changed = 0
            insertions = 0
            deletions = 0
            continue

        if not line.strip() or current is None:
            continue

        parts = line.split("\t")
        if len(parts) >= 3 and parts[0] != "-":
            try:
                added = int(parts[0]) if parts[0] != "-" else 0
                removed = int(parts[1]) if parts[1] != "-" else 0
            except ValueError:
                continue
            files_changed += 1
            insertions += added
            deletions += removed

    if current is not None:
        current["files_changed"] = files_changed
        current["insertions"] = insertions
        current["deletions"] = deletions
        commits.append(current)

    return commits


class GitCollector(BaseCollector):
    source: ClassVar[str] = "git"
    output_filename: ClassVar[str] = "git.json"

    @classmethod
    def source_name(cls) -> str:
        return cls.source

    @classmethod
    def is_enabled(cls, config: dict[str, Any]) -> bool:
        repos = config.get("git", {}).get("repos") or []
        return bool(repos)

    def collect(self, date_str: str) -> dict[str, Any]:
        start, end = day_bounds(date_str, self.timezone)
        git_cfg = self.config.get("git", {})
        repos_cfg = git_cfg.get("repos") or []

        results: list[dict[str, Any]] = []
        for raw in repos_cfg:
            repo_path = Path(str(raw)).expanduser().resolve()
            payload = self._collect_repo(repo_path, start.isoformat(), end.isoformat())
            results.append(payload)
            count = len(payload.get("commits") or [])
            status = payload.get("error") or "ok"
            print(f"  └─ {repo_path.name}: {count} commits ({status})")

        return {
            "date": date_str,
            "timezone": self.timezone,
            "source": self.source,
            "repos": results,
        }

    def _collect_repo(self, repo_path: Path, start_iso: str, end_iso: str) -> dict[str, Any]:
        git_cfg = self.config.get("git", {})
        author_email = (git_cfg.get("author_email") or "").strip()

        if not repo_path.is_dir():
            return {"repo": str(repo_path), "error": "路径不存在", "commits": []}
        if not (repo_path / ".git").exists():
            return {"repo": str(repo_path), "error": "不是 Git 仓库", "commits": []}

        try:
            branch = _run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD").strip()
            remote = _run_git(repo_path, "config", "--get", "remote.origin.url").strip()
        except RuntimeError as exc:
            return {"repo": str(repo_path), "error": str(exc), "commits": []}

        args = [
            "log",
            "--all",
            f"--since={start_iso}",
            f"--until={end_iso}",
            "--pretty=format:COMMIT|%H|%ai|%an|%ae|%D|%s",
            "--numstat",
        ]
        if git_cfg.get("exclude_merges", True):
            args.insert(1, "--no-merges")
        if author_email:
            args.insert(1, f"--author={author_email}")

        try:
            log_text = _run_git(repo_path, *args)
        except RuntimeError as exc:
            return {"repo": str(repo_path), "error": str(exc), "commits": []}

        exclude_patterns = git_cfg.get("exclude_patterns") or []
        commits = []
        for item in _parse_log_output(log_text):
            if _should_exclude(item["message"], exclude_patterns):
                continue
            refs = item.pop("refs", "")
            item["branch"] = _branch_from_decorated_refs(refs) or branch
            item["remote"] = remote
            commits.append(item)

        return {"repo": str(repo_path), "branch": branch, "remote": remote, "commits": commits}

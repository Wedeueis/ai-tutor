"""BundleLogPort backed by the bundle's log.md (WIKI_SPEC.md §9: date-grouped
entries, newest first)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date as date_cls
from pathlib import Path

_TITLE = "# Directory Update Log"


class MarkdownBundleLog:
    def __init__(self, log_path: Path, today_provider: Callable[[], date_cls] = date_cls.today) -> None:
        self._log_path = log_path
        self._today_provider = today_provider

    def append(self, message: str) -> None:
        today = self._today_provider().isoformat()
        content = (
            self._log_path.read_text(encoding="utf-8")
            if self._log_path.exists()
            else f"{_TITLE}\n"
        )
        lines = content.splitlines()
        if not lines or not lines[0].startswith("#"):
            lines = [_TITLE, *lines]

        heading = f"## {today}"
        bullet = f"* {message}"

        if heading in lines:
            index = lines.index(heading)
            lines.insert(index + 1, bullet)
        else:
            insert_at = 1
            while insert_at < len(lines) and lines[insert_at].strip() == "":
                insert_at += 1
            lines[insert_at:insert_at] = ["", heading, bullet]

        self._log_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

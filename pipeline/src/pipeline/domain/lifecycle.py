"""Lifecycle: `status` and `stale_after` (WIKI_SPEC.md §5.4, §5.5)."""

from __future__ import annotations

from datetime import date
from enum import Enum


class Status(str, Enum):
    DRAFT = "draft"
    STABLE = "stable"
    DEPRECATED = "deprecated"


def effective_status(status: str | None) -> Status:
    """Absent `status` => stable (§5.4)."""
    return Status(status) if status else Status.STABLE


def is_stale(stale_after: str | None, today: date) -> bool:
    """A concept is stale when `today >= stale_after` (§5.5). Absent `stale_after`
    => never stale."""
    if not stale_after:
        return False
    return today >= date.fromisoformat(stale_after)

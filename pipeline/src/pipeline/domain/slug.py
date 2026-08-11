"""Turns arbitrary text into a filesystem/URL-safe slug. Pure, no I/O."""

from __future__ import annotations

import re


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "untitled"

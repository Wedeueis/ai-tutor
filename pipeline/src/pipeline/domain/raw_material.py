"""Unprocessed capture-inbox material (vault/raw/ — not part of the OKF bundle)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawItem:
    id: str
    content: str

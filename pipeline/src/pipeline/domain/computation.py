"""Attested Computation value objects (WIKI_SPEC.md §10). Unused until a real
Executor/Attester adapter exists — kept here so the seam is ready."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Parameter:
    name: str
    type: str
    required: bool


@dataclass(frozen=True)
class Receipt:
    """Evidence a run returns, shaped by the concept's `executor.receipt` (§10.2).
    A runtime artifact — never persisted into the bundle."""

    fields: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Verdict:
    """What the attester returns after inspecting a Receipt (§10.2)."""

    passed: bool
    details: str = ""

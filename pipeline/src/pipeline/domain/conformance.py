"""Structural conformance checks (WIKI_SPEC.md §11). The only OKF-mandated rule a
domain object can check (frontmatter parseability is an adapter-level concern, since
by the time a `Concept` exists it already parsed) is a non-empty `type`. Everything
else here is defensive shape-checking of the optional families in §5."""

from __future__ import annotations

from dataclasses import dataclass, field

from pipeline.domain.concept import Concept


@dataclass(frozen=True)
class ConformanceIssue:
    field: str
    message: str


@dataclass(frozen=True)
class ConformanceReport:
    ok: bool
    issues: list[ConformanceIssue] = field(default_factory=list)


class ConformanceChecker:
    def check(self, concept: Concept) -> ConformanceReport:
        issues: list[ConformanceIssue] = []

        if not concept.frontmatter.type or not concept.frontmatter.type.strip():
            issues.append(
                ConformanceIssue("type", "concept must have a non-empty `type` (§11)")
            )

        for event in concept.frontmatter.verified:
            if not event.by or not str(event.by).strip():
                issues.append(
                    ConformanceIssue("verified", "a `verified` entry is missing `by`")
                )

        if concept.frontmatter.status not in (None, "draft", "stable", "deprecated"):
            issues.append(
                ConformanceIssue(
                    "status",
                    f"unrecognized status {concept.frontmatter.status!r} "
                    "(expected draft|stable|deprecated, §5.4)",
                )
            )

        return ConformanceReport(ok=not issues, issues=issues)

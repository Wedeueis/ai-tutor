"""Core OKF concept model (WIKI_SPEC.md §2, §4). Pure domain — no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pipeline.domain.eval import EvalResult


@dataclass(frozen=True)
class ConceptId:
    """A concept's path within the bundle, `.md` suffix removed (WIKI_SPEC.md §2)."""

    value: str

    def __post_init__(self) -> None:
        if not self.value or self.value.endswith(".md"):
            raise ValueError(f"invalid concept id: {self.value!r}")
        # Every ConceptId eventually becomes a filesystem path (see
        # MarkdownConceptRepository._path_for) — reject anything that could
        # escape the vault root (absolute paths, `..`/`.` segments, empty
        # segments from `//`, backslashes) here, once, rather than trusting
        # every caller (including the MCP server, which takes ids from
        # untrusted remote input) to sanitize its own input.
        if self.value.startswith("/") or "\\" in self.value or "\x00" in self.value:
            raise ValueError(f"invalid concept id: {self.value!r}")
        if any(part in ("", ".", "..") for part in self.value.split("/")):
            raise ValueError(f"invalid concept id: {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Actor:
    """`<producer>/<version>` for agents, `human:<id>` for people, `process:<id>` for
    automated processes (WIKI_SPEC.md §7)."""

    value: str

    @property
    def is_human(self) -> bool:
        return self.value.startswith("human:")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Source:
    """One entry in a concept's `sources` frontmatter (WIKI_SPEC.md §5.1)."""

    resource: str
    id: str | None = None
    title: str | None = None
    author: str | None = None
    usage_count: int | None = None
    last_modified: str | None = None
    locator: str | None = None
    """Where *within* `resource` this entry points — `passage 17`, `p. 42`,
    `§3.2`. Display text, deliberately opaque: consumers show it and never
    parse it, and absent means only that the location is unknown.

    Added in OKF v0.3 (§5.1). `id` says *which* entry a footnote cites;
    `locator` says *where in the source* that entry came from."""


@dataclass(frozen=True)
class VerificationEvent:
    """One entry in a concept's `verified` frontmatter (WIKI_SPEC.md §5.2).
    `at` is optional because §11 requires tolerating an entry that omits it —
    the serializer already writes `null` in that case."""

    by: Actor
    at: datetime | None


@dataclass(frozen=True)
class Generated:
    """A concept's `generated` frontmatter: who/what produced it, and when (§5.2)."""

    by: Actor
    at: datetime | None = None


@dataclass
class Frontmatter:
    """A concept's YAML frontmatter block (WIKI_SPEC.md §4.1). `type` is the only
    required field; everything else is optional. Unknown keys are preserved in
    `extra` rather than dropped (§4.1: consumers MUST NOT reject unrecognized keys)."""

    type: str
    title: str | None = None
    description: str | None = None
    resource: str | None = None
    tags: list[str] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)
    generated: Generated | None = None
    verified: list[VerificationEvent] = field(default_factory=list)
    status: str | None = None  # draft | stable | deprecated; absent => stable (§5.4)
    stale_after: str | None = None  # ISO date (§5.5)
    domain: str | None = None  # id of the owning `type: Domain` concept, if triaged
    eval: EvalResult | None = None  # quality-eval audit trail (pipeline/evals/, not a vault concept)
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """A plain, JSON-Schema-validatable dict of the always-present fields plus
        any producer-defined extras. Keeps schema validation decoupled from the
        dataclass shape."""
        data: dict = {"type": self.type, **self.extra}
        if self.title is not None:
            data["title"] = self.title
        if self.description is not None:
            data["description"] = self.description
        if self.resource is not None:
            data["resource"] = self.resource
        if self.tags:
            data["tags"] = list(self.tags)
        if self.status is not None:
            data["status"] = self.status
        if self.stale_after is not None:
            data["stale_after"] = self.stale_after
        if self.domain is not None:
            data["domain"] = self.domain
        if self.eval is not None:
            data["eval"] = {
                "passed": self.eval.passed,
                "average_score": self.eval.average_score,
                "scores": [
                    {"rubric_id": s.rubric_id, "score": s.score, "rationale": s.rationale}
                    for s in self.eval.scores
                ],
            }
        return data


@dataclass
class Concept:
    """One OKF concept: a markdown document with frontmatter + body (§2, §4)."""

    id: ConceptId
    frontmatter: Frontmatter
    body: str


NON_CONTENT_TYPES = {"MOC", "Domain", "Source Document", "Category"}
"""Structural/navigation types (curated link hubs, domain scaffolding,
per-source reference stubs, category hubs) that aren't ingestible content —
excluded from semantic search/candidate matching (IndexConcept),
entity-disambiguation, and quality auditing (AuditConceptQuality). Still
tracked in the metadata store (and, for `Category`, in the link graph — see
`SearchConcepts`' graph-expansion stage), just not treated as "knowledge" a
standalone-quality judgment would make sense against."""


@dataclass(frozen=True)
class LinkGraph:
    """Outgoing and incoming §6 links for one concept — how clusters of
    related concepts become walkable, independent of tags. Both directions
    are derived from the `links` table's raw, regex-extracted markdown link
    targets (see `MetadataRepositoryPort.upsert`/`find_links`), so entries
    are whatever string form the link used (e.g. `/qubits.md`), not
    necessarily a normalized `ConceptId`."""

    concept_id: str
    outgoing: list[str] = field(default_factory=list)
    incoming: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TypedLink:
    """One typed edge in the ontology graph — a Dataview-style inline field
    (`relation_type:: [[target]]`) written directly in a concept's body, e.g.
    `supersedes:: [[/decisions/old-decision]]`. Every typed link is also a
    plain §6 link (it lands in `links` as well as `typed_links`), so it's
    visible in Obsidian's native graph/backlinks with no plugin required."""

    from_id: str
    to_id: str
    relation_type: str

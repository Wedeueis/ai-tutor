"""Composing the tutor's instructions and tool access for one concept.

A **composition root, not a service holding prompt strings** (PRD v3 §5): the
prose lives in `SOUL.md` and in each pedagogy's `SKILL.md`, so adding a way of
teaching is dropping a directory rather than editing this file.

Three layers, in this order (RF2.3):

1. `SOUL.md` — who the tutor is, the same in every session.
2. The pedagogy overlay — how to teach *this* subject.
3. The invariants — composed **last**, and unable to be overridden.

The order is the enforcement. A pedagogy is a markdown file that anyone can
edit; if it could come after the invariants, every guarantee in §2.1 would be
advisory.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from google.adk.skills import Skill, load_skill_from_dir

from tutor.application.invariants import INVARIANTS
from tutor.application.ports.outbound.vault import Concept

logger = logging.getLogger(__name__)

GENERIC_PEDAGOGY = "generic"
"""Mandatory, and the one that runs most often (RF2.6).

Most concepts carry no `domain:` — 11 of 64 in this vault do — so this is the
default path, not a fallback afterthought."""

VAULT_TOOLS: frozenset[str] = frozenset(
    {
        "get_concept",
        "search_wiki",
        "list_concepts",
        "list_types",
        "related_concepts",
        "find_relations",
        "trace_lineage",
        "get_source",
        "find_entity",
    }
)
"""Every tool a pedagogy may draw from: `pipeline`'s read-only MCP surface.

The ceiling, not a default. `allowed-tools` selects a subset of this and can
never extend it (RF2.5) — code execution and diagram tools are deliberately
absent, because a capability decision must not be able to ride in on a
pedagogy file."""


class PedagogyNotFound(RuntimeError):
    """The generic pedagogy is missing. Every other lookup falls back to it, so
    its absence is a broken install rather than a runtime condition."""


class Pedagogy:
    """One `SKILL.md` directory, plus the Domain binding read from its
    frontmatter `metadata`.

    The binding lives with the pedagogy rather than in `config.py` so that
    "adding a pedagogy = drop a directory" is literally true (RF2.1)."""

    def __init__(self, skill: Skill) -> None:
        self._skill = skill

    @property
    def name(self) -> str:
        return str(self._skill.frontmatter.name)

    @property
    def instructions(self) -> str:
        return str(self._skill.instructions)

    @property
    def domains(self) -> tuple[str, ...]:
        raw = (self._skill.frontmatter.metadata or {}).get("domains") or []
        if isinstance(raw, str):
            raw = [raw]
        return tuple(str(domain) for domain in raw)

    @property
    def allowed_tools(self) -> frozenset[str]:
        """The declared subset, intersected with what actually exists.

        Intersecting is the whole mechanism: a pedagogy naming a tool outside
        `VAULT_TOOLS` simply does not get it, so `allowed-tools` can only ever
        narrow. Declaring nothing means the full read-only surface."""
        declared = self._skill.frontmatter.allowed_tools
        if not declared:
            return VAULT_TOOLS

        names = {part.strip() for part in str(declared).split(",") if part.strip()}
        unknown = names - VAULT_TOOLS
        if unknown:
            logger.warning(
                "pedagogy %r declares unavailable tool(s) %s — ignored; "
                "allowed-tools narrows the shared set, it cannot extend it",
                self.name,
                sorted(unknown),
            )
        return frozenset(names & VAULT_TOOLS)


class HermesDomainOrchestrator:
    """Loads the pedagogies once at startup and composes per concept.

    Deliberately **not** ADK's `SkillToolset`: its runtime discovery failed
    outright locally (#12), and discovery solves a problem this does not have —
    the pedagogy set is known when the process starts. The `SKILL.md` *parser*
    is reused, which is what keeps a pedagogy loadable by Hermes-compatible
    tooling (§11)."""

    def __init__(self, pedagogies_dir: Path, soul_path: Path) -> None:
        self._soul = soul_path.read_text(encoding="utf-8").strip()
        self._pedagogies = _load_pedagogies(pedagogies_dir)
        if GENERIC_PEDAGOGY not in self._pedagogies:
            raise PedagogyNotFound(
                f"no {GENERIC_PEDAGOGY!r} pedagogy in {pedagogies_dir} — "
                "it is the default path for every concept without a bound Domain"
            )
        self._by_domain = _index_by_domain(self._pedagogies.values())

    def pedagogy_for(self, concept: Concept) -> Pedagogy:
        """Selected by Domain, deterministically, **before the model is
        invoked** (RF2.2).

        `tutor` never classifies: `pipeline` owns that, and a tutor-side guess
        would be a second, disagreeing opinion about what a concept is (#5). A
        concept with no domain, or a domain nothing is bound to, gets the
        generic pedagogy."""
        if concept.domain and concept.domain in self._by_domain:
            return self._by_domain[concept.domain]
        return self._pedagogies[GENERIC_PEDAGOGY]

    def for_concept(
        self, concept: Concept
    ) -> tuple[Callable[[Any], str], Callable[..., bool]]:
        """The `(InstructionProvider, ToolPredicate)` pair for this concept.

        The instruction is a callable because that is what
        `LlmAgent.instruction` accepts, and because RF2.7 freezes the volatile
        tier at session start: composing here, once, is what stops mastery
        changing mid-dialogue."""
        pedagogy = self.pedagogy_for(concept)
        instruction = self.compose(pedagogy)
        allowed = pedagogy.allowed_tools

        def instruction_provider(_context: Any = None) -> str:
            return instruction

        def tool_predicate(tool: Any, _readonly_context: Any = None) -> bool:
            return getattr(tool, "name", None) in allowed

        return instruction_provider, tool_predicate

    def compose(self, pedagogy: Pedagogy) -> str:
        """Soul, then pedagogy, then invariants — in that order, always."""
        return "\n\n".join([self._soul, pedagogy.instructions.strip(), INVARIANTS])


def _load_pedagogies(pedagogies_dir: Path) -> dict[str, Pedagogy]:
    pedagogies: dict[str, Pedagogy] = {}
    for child in sorted(pedagogies_dir.iterdir()) if pedagogies_dir.exists() else []:
        if not (child / "SKILL.md").is_file():
            continue
        try:
            pedagogy = Pedagogy(load_skill_from_dir(child))
        except Exception:  # noqa: BLE001 - one bad directory must not take the rest
            logger.exception("could not load pedagogy from %s — skipping", child)
            continue
        pedagogies[pedagogy.name] = pedagogy
    return pedagogies


def _index_by_domain(pedagogies: Sequence[Pedagogy] | Any) -> dict[str, Pedagogy]:
    """First binding wins, and a collision is logged rather than resolved
    silently: two pedagogies claiming one Domain is a mistake in the files, and
    picking one quietly would make it very hard to see."""
    index: dict[str, Pedagogy] = {}
    for pedagogy in pedagogies:
        for domain in pedagogy.domains:
            if domain in index:
                logger.warning(
                    "domain %r is claimed by both %r and %r — keeping %r",
                    domain,
                    index[domain].name,
                    pedagogy.name,
                    index[domain].name,
                )
                continue
            index[domain] = pedagogy
    return index

"""What `tutor` is allowed to send outward, and what it is shaped like.

The memory boundary (§2.1) in one sentence: *would this make sense to someone
who never took the session?* Everything in this module passes that test by
construction —

- an **inquiry** is a question about the vault ("nothing here defines *ease
  factor*"; "these two concepts disagree about the ratio"). It says nothing
  about the learner, and anyone reading the vault could have raised it.
- a **proposal** is a concept that came out of teaching. Also learner-free: a
  synthesis is knowledge whether or not anyone was taught with it.

**A learner blindspot has no type here, and that is the enforcement.** "You
keep confusing X with Y" is a reading of the review log, it means nothing to
anyone else, and it belongs to `learner.db` alone. There is no
`Blindspot` dataclass, so there is nothing for a later feature to hand to the
port — a filter that inspects content and decides could be wrong, while a verb
that does not exist cannot be called (NFR5 names this the constraint most
likely to be violated by a well-meaning later feature).

Pure domain: this decides the shape and the filename, and knows nothing about
directories.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

ORIGIN_MARKER = "tutor"
"""What makes tutor-origin material obvious in the inbox at a glance.

`vault/raw/` is mostly PDFs and notes the user dropped there deliberately.
Something that appeared on its own should say so in its own filename, before
anyone opens it."""

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_MAX_SLUG = 60


class InquiryKind(str, Enum):
    """The two things teaching can discover about the *vault* itself.

    Both are automatic — no approval step — because neither creates knowledge:
    they ask a question that a human, or one day a research-and-synthesise flow
    (#15), answers."""

    COVERAGE_GAP = "gap"
    CONTRADICTION = "contradiction"


@dataclass(frozen=True)
class Inquiry:
    """A question about the vault, raised while teaching.

    `concept_ids` are what prompted it — the concepts that disagree, or the
    ones that lean on the undefined term. They are how a person picks up the
    thread later, and for a contradiction they are the whole point."""

    kind: InquiryKind
    title: str
    body: str
    concept_ids: tuple[str, ...] = ()

    def filename(self, on: date) -> str:
        return _filename(on, self.kind.value, self.title)

    def render(self, on: date) -> str:
        return _render(
            title=self.title,
            origin=(
                f"Raised automatically by `{ORIGIN_MARKER}` on {on.isoformat()} "
                f"while teaching — a {self.kind.value.replace('-', ' ')} in the vault, "
                "not knowledge and not captured material."
            ),
            body=self.body,
            concept_ids=self.concept_ids,
            concepts_heading="Concepts that prompted this",
        )


@dataclass(frozen=True)
class Proposal:
    """A derived concept, waiting for a human.

    Unlike an inquiry this does **not** go to the inbox on its own (§2.1).
    `pipeline` remains the only thing that ever creates a concept, and
    approving a proposal is a person moving this file into `vault/raw/` — which
    is why it is written in the same shape as anything else that lands there:
    plain markdown, no frontmatter, approval is `mv`."""

    title: str
    body: str
    concept_ids: tuple[str, ...] = field(default_factory=tuple)
    """What it was synthesised from. Not `sources[]` — this is not a concept
    yet, and pretending otherwise would put frontmatter on a file that must
    stay raw material."""

    def filename(self, on: date) -> str:
        return _filename(on, "concept", self.title)

    def render(self, on: date) -> str:
        return _render(
            title=self.title,
            origin=(
                f"Proposed by `{ORIGIN_MARKER}` on {on.isoformat()} while teaching. "
                "**Awaiting human approval** — approve it by moving this file into "
                "`vault/raw/`."
            ),
            body=self.body,
            concept_ids=self.concept_ids,
            concepts_heading="Synthesised from",
        )


def slugify(text: str) -> str:
    """Lowercase, hyphenated, and **safe as a path segment**.

    Everything outside `[a-z0-9-]` goes, which incidentally removes every way a
    title could climb out of its directory. That is not a happy accident worth
    relying on alone — the adapter checks containment too — but a slug that can
    contain a separator is a bug waiting for a title with a slash in it."""
    slug = _SLUG_STRIP.sub("-", text.strip().lower()).strip("-")
    return slug[:_MAX_SLUG].rstrip("-") or "untitled"


def _filename(on: date, kind: str, title: str) -> str:
    """`<date>-tutor-<kind>-<slug>.md` — sorts chronologically, says who wrote
    it, and says what it is, in that order, because that is the order someone
    scanning a directory listing needs them."""
    return f"{on.isoformat()}-{ORIGIN_MARKER}-{kind}-{slugify(title)}.md"


def _render(
    *,
    title: str,
    origin: str,
    body: str,
    concept_ids: tuple[str, ...],
    concepts_heading: str,
) -> str:
    """Plain markdown, **no frontmatter**.

    Files in `vault/raw/` carry none (CLAUDE.md): this is a capture surface, not
    the bundle. Adding frontmatter would make it look like a concept, and
    `tutor` never writes the bundle (#8)."""
    lines = [f"# {title}", "", f"> {origin}", "", body.strip()]
    if concept_ids:
        lines += ["", f"## {concepts_heading}", ""]
        lines += [f"- [{concept_id}](/{concept_id}.md)" for concept_id in concept_ids]
    return "\n".join(lines).rstrip() + "\n"

"""How deep the learner intends to go in one Category, and what counts as
having got there.

Learner intent, so **episodic**: the vault never records what someone wants to
specialise in. Bound to a `type: Category` rather than a Domain — the
granularity that expresses "specialise in GraphRAG, stay aware of the rest of
ML" (PRD v3 RF3.3).

Pure domain. No I/O, nothing to mock."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from tutor.domain.scheduling import SchedulerState


class DepthLevel(str, Enum):
    AWARE = "aware"
    WORKING = "working"
    SPECIALIST = "specialist"


DEFAULT_DEPTH_LEVEL = DepthLevel.AWARE
"""What an untargeted Category resolves to.

Not a placeholder: new Categories arrive from ingest unseen, and defaulting to
anything deeper would commit the learner to study they never chose (PRD v3
RF3.3)."""


@dataclass(frozen=True)
class DepthRequirement:
    """What one level asks for.

    The threshold is **days of interval**, never a bare float. A stability of
    "21.0" means nothing to anyone; "you can still recall this three weeks
    later" is a claim a person can agree or disagree with, which is the only
    way these numbers ever get corrected."""

    stability_days: float
    requires_discursive: bool = False
    """Whether a free-text answer graded against a rubric is needed, as opposed
    to a self-reported recall grade. Only `specialist` asks for it: explaining
    something in your own words is different evidence from recognising it, and
    it is the difference the top level is meant to capture (RF4.4)."""

    description: str = ""


REQUIREMENTS: dict[DepthLevel, DepthRequirement] = {
    DepthLevel.AWARE: DepthRequirement(
        stability_days=7,
        description="Recognise it and know roughly what it is for a week later.",
    ),
    DepthLevel.WORKING: DepthRequirement(
        stability_days=30,
        description="Recall it unprompted a month later, well enough to use it.",
    ),
    DepthLevel.SPECIALIST: DepthRequirement(
        stability_days=180,
        requires_discursive=True,
        description=(
            "Explain it in your own words, and still hold it six months later."
        ),
    ),
}
"""Thresholds chosen so the levels are *qualitatively* different rather than
evenly spaced: a week, a month, half a year. Nothing here is fitted — these are
a starting position meant to be argued with once there is a review history to
argue from."""


def requirement_for(level: DepthLevel) -> DepthRequirement:
    return REQUIREMENTS[level]


def deepest(levels: Iterable[DepthLevel]) -> DepthLevel:
    """The most demanding of several targets, or `aware` if there are none.

    A concept belongs to as many Categories as `pipeline` classified it into,
    and each can carry its own target. Taking the deepest is the only rule
    under which *adding* a Category cannot quietly lower what is asked of a
    concept — otherwise "specialise in GraphRAG" would be undone the moment
    those concepts were also filed under a broad `aware` Category.

    Ordered by the stability threshold rather than by declaration order, so the
    ordering keeps meaning if a level is ever inserted between two others."""
    return max(
        levels,
        key=lambda level: REQUIREMENTS[level].stability_days,
        default=DEFAULT_DEPTH_LEVEL,
    )


def meets_target(
    state: SchedulerState | None,
    level: DepthLevel,
    has_discursive_evidence: bool = False,
) -> bool:
    """Has the learner reached `level` on this concept?

    **Keyed on stability, not retrievability** — the whole point of the
    decision in #18. Stability is durability and moves only when you review, so
    a prerequisite satisfied in March is still satisfied in June. Retrievability
    decays with the calendar alone, and keying mastery on it would reshuffle
    the study plan every morning with no new evidence.

    This is what replaced `MasteryScore`: "mastered" is a predicate over FSRS
    state and a target, not a stored number that would start going stale the
    moment it was written.

    A concept never reviewed has no state, and that is a `False` rather than an
    error — the study plan asks this about everything it is considering."""
    if state is None or state.stability is None:
        return False

    requirement = REQUIREMENTS[level]
    if requirement.requires_discursive and not has_discursive_evidence:
        return False
    return state.stability >= requirement.stability_days

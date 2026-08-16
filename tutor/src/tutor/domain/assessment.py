"""Grading a learner's answer, and turning that grade into an FSRS rating.

Pure domain. No I/O, nothing to mock (NFR7).

**These rubrics are `tutor`'s own, and the shape is mirrored rather than
imported** (RF4.5). `pipeline/evals/` scores whether a *concept* is well
written — grounded in its source, not too thin, not a verbatim copy. A
learner's answer is a different subject, and scoring it with those rubrics
would be scoring the wrong thing with a straight face. The field names are
kept identical anyway (they are ADK's own `eval_rubrics` shape, which
`pipeline` also mirrors) so the two read as one system side by side; the
import is forbidden by rule 1 regardless — `tutor` does not depend on
`pipeline`.

**The model scores rubrics; this code picks the rating.** That split is the
point of RF4.4. A model asked directly for "AGAIN/HARD/GOOD/EASY" would make
next month's schedule depend on its mood, and the mapping would be
unreviewable — nobody can diff a prompt's judgement. Here it is a pure
function anyone can read, argue with and test without a model running.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tutor.domain.scheduling import Rating


@dataclass(frozen=True)
class RubricContent:
    text_property: str


@dataclass(frozen=True)
class Rubric:
    """One criterion an answer is judged against.

    Generated per review alongside the question and thrown away with it
    (RF4.3) — which is why `rubric_id` only has to be unique within one
    exchange, and why nothing here has a version."""

    rubric_id: str
    rubric_content: RubricContent
    description: str | None = None
    type: str | None = None


@dataclass(frozen=True)
class RubricScore:
    rubric_id: str
    score: float | None = None
    """0.0–1.0, or None when the grader could not judge this criterion. A
    criterion nobody could judge is left out of the average rather than
    counted as a zero — a grader's silence is not the learner's failure."""

    rationale: str | None = None


@dataclass(frozen=True)
class EvalResult:
    scores: list[RubricScore] = field(default_factory=list)
    average_score: float = 0.0
    graded: bool = False
    """Whether anything was actually scored. Distinct from a low average: an
    empty grading is a broken grader, and the two must not collapse into the
    same value (see `rating_for`)."""


def aggregate_scores(scores: list[RubricScore]) -> EvalResult:
    """Roll individual rubric scores into one result.

    Unweighted mean, deliberately. Weighting criteria against each other is a
    pedagogical claim, and there is no evidence to make it from yet — an
    invented weighting would be harder to argue with than an obvious one."""
    numeric = [score.score for score in scores if score.score is not None]
    if not numeric:
        return EvalResult(scores=list(scores), average_score=0.0, graded=False)
    return EvalResult(
        scores=list(scores),
        average_score=sum(numeric) / len(numeric),
        graded=True,
    )


AGAIN_BELOW = 0.5
"""Under half the criteria met is not recall. FSRS's `AGAIN` means the memory
was not retrieved, and half an answer is not a retrieved one."""

HARD_BELOW = 0.75
"""Retrieved, but with gaps a reviewer would notice. `HARD` shortens the next
interval without treating the review as a lapse."""

EASY_FROM = 0.95
"""Effectively complete. `EASY` lengthens the interval sharply, so the bar is
deliberately near the top — "nothing to add" rather than "good"."""


class NotGraded(ValueError):
    """Nothing was scored, so there is no rating to derive.

    Deliberately an error rather than `AGAIN`. An empty grading means the
    grader failed, and writing `AGAIN` for it would record a lapse the learner
    never had — permanently, in an append-only log, with FSRS then shortening
    every subsequent interval on that evidence. A review that could not be
    graded must not become a review event at all."""


def rating_for(result: EvalResult) -> Rating:
    """Map a rubric rollup to one FSRS rating. Deterministic and pure (RF4.4).

    The thresholds are a starting position, chosen to be *arguable* rather than
    fitted: there is no review history to fit them against yet, and the honest
    version of that is three named constants a person can disagree with."""
    if not result.graded:
        raise NotGraded("no rubric was scored, so no rating can be derived")

    if result.average_score < AGAIN_BELOW:
        return Rating.AGAIN
    if result.average_score < HARD_BELOW:
        return Rating.HARD
    if result.average_score < EASY_FROM:
        return Rating.GOOD
    return Rating.EASY


def render_rubrics(rubrics: list[Rubric]) -> str:
    """The rubrics as the text stored on the review event.

    Stored as text, not as a pointer: the rubric was generated for this one
    exchange and discarded, so there is nothing left to point *at*. A row has
    to stay independently interpretable years later."""
    return "\n".join(
        f"- {rubric.rubric_id}: {rubric.rubric_content.text_property}"
        for rubric in rubrics
    )


def render_grade(result: EvalResult) -> str:
    """The grade as the text stored on the review event: the rollup, then each
    criterion with the grader's reason. What a person would need to see to
    decide the grade was unfair."""
    lines = [f"average {result.average_score:.2f}"]
    for score in result.scores:
        value = "unjudged" if score.score is None else f"{score.score:.2f}"
        rationale = f" — {score.rationale}" if score.rationale else ""
        lines.append(f"- {score.rubric_id}: {value}{rationale}")
    return "\n".join(lines)

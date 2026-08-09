"""Quality-eval rubric model, mirrored field-for-field from Google ADK's
`eval_rubrics.py`/`eval_case.py` so a `rubrics` list is directly interchangeable
with an ADK `.evalset.json` / `EvalCase.rubrics` — no lossy transform needed at
the boundary. Pure domain — no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RubricContent:
    text_property: str


@dataclass(frozen=True)
class Rubric:
    rubric_id: str
    rubric_content: RubricContent
    description: str | None = None
    type: str | None = None


@dataclass(frozen=True)
class RubricScore:
    rubric_id: str
    score: float | None = None
    rationale: str | None = None


@dataclass(frozen=True)
class EvalResult:
    """The deterministic rollup of a set of RubricScores — the LLM only scores
    individual rubrics; this pass/fail decision is plain domain logic."""

    scores: list[RubricScore] = field(default_factory=list)
    average_score: float = 0.0
    passed: bool = False


DEFAULT_EVAL_THRESHOLD = 0.7


def aggregate_scores(
    scores: list[RubricScore], threshold: float = DEFAULT_EVAL_THRESHOLD
) -> EvalResult:
    numeric = [s.score for s in scores if s.score is not None]
    average = sum(numeric) / len(numeric) if numeric else 0.0
    return EvalResult(scores=list(scores), average_score=average, passed=average >= threshold)

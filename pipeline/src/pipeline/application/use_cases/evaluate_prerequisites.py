"""Measures the prerequisite gate's precision against human-labelled pairs
(`pipeline eval-prerequisites`, RF1.3).

Without this the gate is an LLM grading an LLM: the rubrics are themselves
scored by the same model whose judgement they are supposed to constrain, so
nothing external says whether the `requires::` tier is trustworthy.

**Precision, not accuracy or F1.** A wrong `requires::` edge sends the learner
to study something they do not need and nothing downstream signals it; a
missed one only means the planner does not know about a dependency it could
have used. Recall is deliberately unconstrained (decided in #14) — so is the
`may_require::` tier, which nothing reads."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from pipeline.application.ports.concept_repository import ConceptRepositoryPort
from pipeline.application.ports.eval_rubrics_repository import EvalRubricsRepositoryPort
from pipeline.application.ports.skills.prerequisite_judgement import (
    PrerequisiteJudgementSkillPort,
)
from pipeline.domain.agent import DraftConcept
from pipeline.domain.concept import ConceptId
from pipeline.domain.eval import RubricScore
from pipeline.domain.prerequisites import (
    PrerequisiteCandidate,
    PrerequisiteTier,
    select_prerequisites,
)

DEFAULT_PRECISION_BAR = 0.9
GOLD_SET_FILENAME = "prerequisites-gold.json"
PREREQUISITE_RUBRICS = "prerequisites"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GoldPair:
    source: str
    target: str
    is_prerequisite: bool


@dataclass(frozen=True)
class PairOutcome:
    pair: GoldPair
    tier: PrerequisiteTier | None
    """None when the skill declined to assess the pair at all."""
    average_score: float
    scores: list[RubricScore] = field(default_factory=list)
    """Kept per rubric, not just rolled up. When precision misses the bar the
    next question is always *which criterion failed to discriminate*, and an
    average cannot answer it."""

    @property
    def predicted_requires(self) -> bool:
        return self.tier is PrerequisiteTier.REQUIRES

    @property
    def correct(self) -> bool:
        return self.predicted_requires == self.pair.is_prerequisite


@dataclass(frozen=True)
class PrecisionReport:
    outcomes: list[PairOutcome] = field(default_factory=list)
    bar: float = DEFAULT_PRECISION_BAR

    @property
    def predicted(self) -> list[PairOutcome]:
        """Pairs the gate put in the `requires::` tier — precision's denominator."""
        return [o for o in self.outcomes if o.predicted_requires]

    @property
    def true_positives(self) -> list[PairOutcome]:
        return [o for o in self.predicted if o.pair.is_prerequisite]

    @property
    def false_positives(self) -> list[PairOutcome]:
        """The ones that matter. Each is a wrong edge a study plan would walk."""
        return [o for o in self.predicted if not o.pair.is_prerequisite]

    @property
    def precision(self) -> float:
        """A gate that emits nothing scores 0.0, not 1.0. Vacuous precision is
        not evidence the rubrics work — it is evidence they were never
        exercised, and the empty-denominator convention would hide that behind
        a passing number."""
        if not self.predicted:
            return 0.0
        return len(self.true_positives) / len(self.predicted)

    @property
    def recall(self) -> float:
        """Reported for context only — never gated on (#14)."""
        actual = [o for o in self.outcomes if o.pair.is_prerequisite]
        if not actual:
            return 0.0
        return sum(1 for o in actual if o.predicted_requires) / len(actual)

    @property
    def passed(self) -> bool:
        return self.precision >= self.bar


class EvaluatePrerequisites:
    def __init__(
        self,
        concept_repository: ConceptRepositoryPort,
        prerequisite_judgement: PrerequisiteJudgementSkillPort,
        eval_rubrics_repository: EvalRubricsRepositoryPort,
        evals_dir: Path,
        threshold: float,
        bar: float = DEFAULT_PRECISION_BAR,
    ) -> None:
        self._concept_repository = concept_repository
        self._prerequisite_judgement = prerequisite_judgement
        self._eval_rubrics_repository = eval_rubrics_repository
        self._evals_dir = evals_dir
        self._threshold = threshold
        self._bar = bar

    def run(self) -> PrecisionReport:
        rubrics = self._eval_rubrics_repository.load_named(PREREQUISITE_RUBRICS)
        if not rubrics:
            raise ValueError(f"no '{PREREQUISITE_RUBRICS}' rubrics found in {self._evals_dir}")

        outcomes = [self._judge(pair, rubrics) for pair in self._load_gold_set()]
        return PrecisionReport(outcomes=outcomes, bar=self._bar)

    def _judge(self, pair: GoldPair, rubrics: list) -> PairOutcome:
        """One pair, judged exactly the way ingest judges one — same skill,
        same rubrics, same threshold, same rollup. A measurement that took a
        shortcut here would be measuring something other than the gate."""
        source = self._concept_repository.load(ConceptId(pair.source))
        target = self._concept_repository.load(ConceptId(pair.target))
        draft = DraftConcept(
            frontmatter=source.frontmatter, body=source.body, source_raw_id=pair.source
        )
        candidate = PrerequisiteCandidate(
            concept_id=target.id,
            title=target.frontmatter.title,
            description=target.frontmatter.description,
        )

        assessments = self._prerequisite_judgement.judge(draft, [candidate], rubrics)
        edges = select_prerequisites(
            source_id=pair.source, assessments=assessments, threshold=self._threshold
        )
        if not edges:
            return PairOutcome(pair=pair, tier=None, average_score=0.0)
        return PairOutcome(
            pair=pair,
            tier=edges[0].tier,
            average_score=edges[0].eval.average_score,
            scores=list(edges[0].eval.scores),
        )

    def _load_gold_set(self) -> list[GoldPair]:
        path = self._evals_dir / GOLD_SET_FILENAME
        if not path.exists():
            raise FileNotFoundError(
                f"no gold set at {path} — the gate cannot be measured without one"
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [
            GoldPair(
                source=entry["source"],
                target=entry["target"],
                is_prerequisite=bool(entry["is_prerequisite"]),
            )
            for entry in raw
        ]

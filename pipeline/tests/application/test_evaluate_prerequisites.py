"""Precision measurement against the gold set (RF1.3).

The arithmetic is what's under test here — whether the number the ship gate
reads is the right number. The gate's actual behaviour against a real model is
what `pipeline eval-prerequisites` measures, and that needs Ollama."""

import json

import pytest

from pipeline.application.use_cases.evaluate_prerequisites import (
    EvaluatePrerequisites,
    GoldPair,
    PairOutcome,
    PrecisionReport,
)
from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from pipeline.domain.eval import Rubric, RubricContent, RubricScore
from pipeline.domain.prerequisites import PrerequisiteTier
from tests.application.fakes import (
    FakeConceptRepository,
    FakeEvalRubricsRepository,
    FakePrerequisiteJudgementSkill,
)

RUBRIC = Rubric("blocks", RubricContent("Must be required."))


def _outcome(is_prerequisite: bool, tier: PrerequisiteTier | None) -> PairOutcome:
    return PairOutcome(
        pair=GoldPair(source="a", target="b", is_prerequisite=is_prerequisite),
        tier=tier,
        average_score=0.0,
    )


# --- the number the ship gate reads --------------------------------------


def test_precision_counts_only_the_requires_tier():
    """`may_require::` is inert — nothing reads it, so emitting one is neither
    a hit nor a miss."""
    report = PrecisionReport(
        outcomes=[
            _outcome(True, PrerequisiteTier.REQUIRES),
            _outcome(False, PrerequisiteTier.MAY_REQUIRE),
            _outcome(True, PrerequisiteTier.MAY_REQUIRE),
        ]
    )

    assert len(report.predicted) == 1
    assert report.precision == 1.0


def test_a_wrong_requires_edge_drives_precision_down():
    report = PrecisionReport(
        outcomes=[
            _outcome(True, PrerequisiteTier.REQUIRES),
            _outcome(True, PrerequisiteTier.REQUIRES),
            _outcome(True, PrerequisiteTier.REQUIRES),
            _outcome(False, PrerequisiteTier.REQUIRES),
        ]
    )

    assert report.precision == 0.75
    assert [o.pair.is_prerequisite for o in report.false_positives] == [False]
    assert report.passed is False


def test_a_gate_that_emits_nothing_scores_zero_not_one():
    """The empty-denominator convention would report 1.0 and pass the bar.
    Emitting nothing is not evidence the rubrics work — it is evidence they
    were never exercised."""
    report = PrecisionReport(outcomes=[_outcome(True, None), _outcome(False, None)])

    assert report.precision == 0.0
    assert report.passed is False


def test_recall_is_reported_but_never_gates():
    report = PrecisionReport(
        outcomes=[
            _outcome(True, PrerequisiteTier.REQUIRES),
            _outcome(True, PrerequisiteTier.MAY_REQUIRE),
            _outcome(True, PrerequisiteTier.MAY_REQUIRE),
        ]
    )

    assert report.recall == pytest.approx(1 / 3)
    assert report.precision == 1.0
    assert report.passed is True  # precision alone decides


def test_the_bar_is_inclusive():
    report = PrecisionReport(
        outcomes=[
            *[_outcome(True, PrerequisiteTier.REQUIRES) for _ in range(9)],
            _outcome(False, PrerequisiteTier.REQUIRES),
        ]
    )

    assert report.precision == pytest.approx(0.9)
    assert report.passed is True


# --- the run ------------------------------------------------------------


def _build(tmp_path, pairs, assessments_by_target, rubrics=(RUBRIC,), threshold=0.7):
    (tmp_path / "prerequisites-gold.json").write_text(json.dumps(pairs), encoding="utf-8")

    repository = FakeConceptRepository()
    for concept_id in {p["source"] for p in pairs} | {p["target"] for p in pairs}:
        repository.save(
            Concept(
                id=ConceptId(concept_id),
                frontmatter=Frontmatter(type="Concept", title=concept_id),
                body=f"About {concept_id}.",
            )
        )

    return EvaluatePrerequisites(
        concept_repository=repository,
        prerequisite_judgement=FakePrerequisiteJudgementSkill(assessments_by_target),
        eval_rubrics_repository=FakeEvalRubricsRepository(
            named_rubrics={"prerequisites": list(rubrics)}
        ),
        evals_dir=tmp_path,
        threshold=threshold,
    )


def test_a_pair_is_judged_the_same_way_ingest_judges_one(tmp_path):
    """Same skill, same rubrics, same threshold, same rollup — a shortcut here
    would measure something other than the gate."""
    use_case = _build(
        tmp_path,
        pairs=[{"source": "multi-head-attention", "target": "attention", "is_prerequisite": True}],
        assessments_by_target={"attention": [RubricScore("blocks", 0.9, "required")]},
    )

    report = use_case.run()

    assert report.outcomes[0].tier is PrerequisiteTier.REQUIRES
    assert report.precision == 1.0
    assert report.passed is True


def test_a_hard_negative_the_gate_accepts_shows_up_as_a_false_positive(tmp_path):
    use_case = _build(
        tmp_path,
        pairs=[
            {"source": "cold-brew", "target": "attention", "is_prerequisite": True},
            {"source": "cold-brew", "target": "pour-over", "is_prerequisite": False},
        ],
        assessments_by_target={
            "attention": [RubricScore("blocks", 0.9, "required")],
            "pour-over": [RubricScore("blocks", 0.9, "wrongly confident")],
        },
    )

    report = use_case.run()

    assert report.precision == 0.5
    assert report.passed is False
    assert report.false_positives[0].pair.target == "pour-over"


def test_a_missing_gold_set_is_an_error_not_an_empty_pass(tmp_path):
    use_case = _build(tmp_path, pairs=[], assessments_by_target={})
    (tmp_path / "prerequisites-gold.json").unlink()

    with pytest.raises(FileNotFoundError, match="no gold set"):
        use_case.run()


def test_missing_rubrics_are_an_error_not_a_silent_zero(tmp_path):
    use_case = _build(
        tmp_path,
        pairs=[{"source": "a", "target": "b", "is_prerequisite": True}],
        assessments_by_target={},
        rubrics=(),
    )

    with pytest.raises(ValueError, match="no 'prerequisites' rubrics"):
        use_case.run()


# --- direction (ADR 0002) ------------------------------------------------


def test_the_gold_set_reads_source_requires_target(tmp_path):
    """ADR 0002. The convention is one word wide and reverses cleanly, and a
    transposed gold set already cost a full measurement cycle: it read 0.517
    on a weak model (looking like a tuning problem) and 0.000 on a capable one,
    where the corrected set reads 1.000."""
    use_case = _build(
        tmp_path,
        pairs=[
            {
                "source": "multi-head-attention",
                "target": "scaled-dot-product-attention",
                "is_prerequisite": True,
            }
        ],
        # The skill is keyed by *target*: this canned score is returned only if
        # the dependent was offered as the source and its prerequisite as the
        # candidate. Transposing the convention would score the other id.
        assessments_by_target={
            "scaled-dot-product-attention": [RubricScore("blocks", 0.9, "required")]
        },
    )

    report = use_case.run()

    assert report.outcomes[0].tier is PrerequisiteTier.REQUIRES
    assert report.precision == 1.0


def test_the_real_gold_set_states_the_dependent_first():
    """Guards the shipped file itself, not just the machinery. Checks a pair
    whose direction is unambiguous: a paper's contribution cannot be a
    prerequisite of the mechanism it introduced."""
    import json
    from pathlib import Path

    evals_dir = Path(__file__).resolve().parents[2] / "evals"
    pairs = json.loads((evals_dir / "prerequisites-gold.json").read_text())
    by_pair = {(p["source"], p["target"]): p["is_prerequisite"] for p in pairs}

    assert by_pair[("attention-is-all-you-need", "self-attention")] is True
    assert by_pair[("dependencyextractor", "dependency-parsing")] is True
    # The reverse of a true pair must be present as a hard negative — without
    # reversed pairs a transposition is undetectable (ADR 0002).
    assert by_pair[("dependency-parsing", "dependencyextractor")] is False

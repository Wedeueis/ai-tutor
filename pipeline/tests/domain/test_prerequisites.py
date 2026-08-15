"""The prerequisite gate and its body emission — pure domain, no fakes."""

import pytest

from pipeline.domain.concept import ConceptId
from pipeline.domain.eval import RubricScore
from pipeline.domain.linking import add_prerequisite_links
from pipeline.domain.prerequisites import (
    PrerequisiteAssessment,
    PrerequisiteEdge,
    PrerequisiteTier,
    select_prerequisites,
)

THRESHOLD = 0.7


def _scores(*values: float | None) -> list[RubricScore]:
    return [RubricScore(f"r{i}", value, "because") for i, value in enumerate(values)]


def _assessment(target: str, *values: float | None) -> PrerequisiteAssessment:
    return PrerequisiteAssessment(target_id=ConceptId(target), scores=_scores(*values))


def _select(*assessments, source_id="espresso-extraction", reachable_by=None):
    return select_prerequisites(
        source_id=source_id,
        assessments=list(assessments),
        threshold=THRESHOLD,
        reachable_by=reachable_by,
    )


# --- the two-tier gate ---------------------------------------------------


def test_scores_above_threshold_earn_the_requires_tier():
    edges = _select(_assessment("water-temperature", 0.9, 0.8, 0.9))

    assert [e.tier for e in edges] == [PrerequisiteTier.REQUIRES]
    assert edges[0].relation_type == "requires"


def test_scores_below_threshold_are_recorded_as_may_require():
    edges = _select(_assessment("latte-art", 0.4, 0.2, 0.3))

    assert [e.tier for e in edges] == [PrerequisiteTier.MAY_REQUIRE]
    assert edges[0].relation_type == "may_require"


def test_a_borderline_edge_is_decided_by_the_average_not_by_any_one_rubric():
    # 0.9 + 0.9 + 0.3 averages to 0.7, exactly the threshold.
    edges = _select(_assessment("grind-size", 0.9, 0.9, 0.3))

    assert edges[0].tier is PrerequisiteTier.REQUIRES
    assert edges[0].eval.average_score == pytest.approx(0.7)


def test_an_unscored_rubric_caps_the_edge_at_may_require():
    """`aggregate_scores` averages only the scores it was given, so a model
    that answered one rubric at 1.0 and skipped the rest would otherwise pass
    the gate on a single opinion. Precision is the bar here (RF1.3)."""
    edges = _select(_assessment("water-chemistry", 1.0, None, None))

    assert edges[0].eval.average_score == 1.0  # the shared rollup still says pass
    assert edges[0].tier is PrerequisiteTier.MAY_REQUIRE  # the gate does not


def test_an_assessment_with_no_scores_at_all_is_may_require():
    edges = _select(PrerequisiteAssessment(target_id=ConceptId("mystery")))

    assert edges[0].tier is PrerequisiteTier.MAY_REQUIRE


# --- structural guards ---------------------------------------------------


def test_a_self_edge_is_dropped_rather_than_recorded():
    edges = _select(_assessment("espresso-extraction", 0.9, 0.9, 0.9))

    assert edges == []


def test_an_edge_that_would_close_a_cycle_is_demoted_not_dropped():
    """The judgement was made and is worth a human's review, but the
    `requires::` tier — the only one consumers walk — has to stay acyclic."""
    edges = _select(
        _assessment("grind-size", 0.9, 0.9, 0.9),
        reachable_by={"grind-size": {"espresso-extraction"}},
    )

    assert [e.tier for e in edges] == [PrerequisiteTier.MAY_REQUIRE]
    assert edges[0].target_id == ConceptId("grind-size")


def test_a_cycle_only_demotes_the_edge_that_closes_it():
    edges = _select(
        _assessment("grind-size", 0.9, 0.9, 0.9),
        _assessment("water-temperature", 0.9, 0.9, 0.9),
        reachable_by={"grind-size": {"espresso-extraction"}},
    )

    by_target = {str(e.target_id): e.tier for e in edges}
    assert by_target == {
        "grind-size": PrerequisiteTier.MAY_REQUIRE,
        "water-temperature": PrerequisiteTier.REQUIRES,
    }


def test_a_reachable_target_does_not_demote_an_already_failing_edge():
    edges = _select(
        _assessment("grind-size", 0.1, 0.1, 0.1),
        reachable_by={"grind-size": {"espresso-extraction"}},
    )

    assert edges[0].tier is PrerequisiteTier.MAY_REQUIRE


def test_no_assessments_means_no_edges():
    assert _select() == []


# --- body emission -------------------------------------------------------


def _edge(target: str, tier: PrerequisiteTier = PrerequisiteTier.REQUIRES) -> PrerequisiteEdge:
    from pipeline.domain.eval import EvalResult

    return PrerequisiteEdge(target_id=ConceptId(target), tier=tier, eval=EvalResult())


def test_an_edge_is_written_in_the_exact_shape_the_typed_link_parser_expects():
    """`SqliteMetadataRepository` scrapes typed links with
    `^([a-z][a-z0-9_-]*):: \\[\\[([^\\]]+)\\]\\]$`. A line that doesn't match is
    silently not an edge — it renders fine and never reaches `typed_links`."""
    import re

    pattern = re.compile(r"^([a-z][a-z0-9_-]*):: \[\[([^\]]+)\]\]$", re.MULTILINE)
    body = add_prerequisite_links("Some body.", [_edge("water-temperature")])

    assert pattern.findall(body) == [("requires", "/water-temperature")]


def test_both_tiers_are_emitted_each_on_its_own_line():
    import re

    pattern = re.compile(r"^([a-z][a-z0-9_-]*):: \[\[([^\]]+)\]\]$", re.MULTILINE)
    body = add_prerequisite_links(
        "Some body.",
        [_edge("water-temperature"), _edge("latte-art", PrerequisiteTier.MAY_REQUIRE)],
    )

    assert pattern.findall(body) == [
        ("requires", "/water-temperature"),
        ("may_require", "/latte-art"),
    ]


def test_emission_is_idempotent():
    once = add_prerequisite_links("Some body.", [_edge("water-temperature")])
    twice = add_prerequisite_links(once, [_edge("water-temperature")])

    assert twice == once


def test_a_target_already_linked_is_not_retiered_on_a_second_pass():
    """Dedupe is by target, not by rendered line — otherwise a backfill would
    append a second, contradicting line for the same pair."""
    body = add_prerequisite_links("Some body.", [_edge("grind-size")])
    again = add_prerequisite_links(body, [_edge("grind-size", PrerequisiteTier.MAY_REQUIRE)])

    assert again == body
    assert "may_require" not in again


def test_prerequisites_are_inserted_before_a_trailing_related_section():
    """`## Related` stays last — the invariant every body mutation in
    `domain/linking.py` maintains."""
    body = "Some body.\n\n## Related\n\n- [Qubits](/qubits.md)\n"

    updated = add_prerequisite_links(body, [_edge("water-temperature")])

    assert updated.index("## Prerequisites") < updated.index("## Related")
    assert updated.index("requires:: [[/water-temperature]]") < updated.index("## Related")


def test_a_second_edge_joins_the_existing_prerequisites_section():
    body = add_prerequisite_links(
        "Some body.\n\n## Related\n\n- [Qubits](/qubits.md)\n", [_edge("water-temperature")]
    )

    updated = add_prerequisite_links(body, [_edge("grind-size")])

    assert updated.count("## Prerequisites") == 1
    assert updated.index("requires:: [[/grind-size]]") < updated.index("## Related")


def test_no_edges_leaves_the_body_untouched():
    assert add_prerequisite_links("Some body.", []) == "Some body."

"""Fit to the bundle (RF1.6) — pure domain, no fakes, no I/O.

Accepting is the default here, and almost every test below is really asking
the same question: does this uncertainty resolve toward accepting? Rejecting
drops the draft and keeps only a log line, so it has to fire on positive
evidence rather than on absence."""

from pipeline.domain.relevance import (
    DEFAULT_REDUNDANCY_THRESHOLD,
    MIN_BUNDLE_FOR_TOPICALITY,
    RelevanceEvidence,
    judge_relevance,
)

ESTABLISHED = MIN_BUNDLE_FOR_TOPICALITY + 40


def _evidence(**overrides) -> RelevanceEvidence:
    defaults = dict(bundle_size=ESTABLISHED, nearest_similarity=0.5)
    return RelevanceEvidence(**{**defaults, **overrides})


# --- the happy path ------------------------------------------------------


def test_a_draft_that_neither_duplicates_nor_wanders_is_accepted():
    verdict = judge_relevance(_evidence(nearest_similarity=0.5))

    assert verdict.accepted is True


# --- redundancy ----------------------------------------------------------


def test_a_near_identical_draft_is_rejected_as_already_covered():
    verdict = judge_relevance(
        _evidence(nearest_similarity=0.98, nearest_concept_id="self-attention")
    )

    assert verdict.accepted is False
    assert "already covered by self-attention" in verdict.reason


def test_the_redundancy_bar_sits_far_above_the_merge_bar():
    """Disambiguation already merges at 0.75 confidence when it judges two
    things the same entity. Anything reaching this gate was explicitly judged
    a *different* entity, so overriding that takes near-identity — a draft at
    0.9 similarity is a related concept, not a duplicate."""
    assert DEFAULT_REDUNDANCY_THRESHOLD >= 0.9

    assert judge_relevance(_evidence(nearest_similarity=0.90)).accepted is True


def test_redundancy_is_judged_before_topicality():
    """A tiny bundle cannot make a draft off-topic, but it can still already
    contain the same thing."""
    verdict = judge_relevance(_evidence(bundle_size=2, nearest_similarity=0.99))

    assert verdict.accepted is False
    assert "already covered" in verdict.reason


# --- off-topic -----------------------------------------------------------


def test_a_draft_unrelated_to_everything_is_rejected_as_off_topic():
    verdict = judge_relevance(_evidence(nearest_similarity=0.02))

    assert verdict.accepted is False
    assert "unrelated to anything in the bundle" in verdict.reason


def test_nothing_is_off_topic_in_a_bundle_too_young_to_have_a_topic():
    """Without this, the gate would reject the fourth concept of a new vault
    for not resembling the first three."""
    verdict = judge_relevance(
        _evidence(bundle_size=MIN_BUNDLE_FOR_TOPICALITY - 1, nearest_similarity=0.0)
    )

    assert verdict.accepted is True
    assert "has not established a topic yet" in verdict.reason


def test_the_topicality_floor_is_low_enough_to_let_a_vault_grow():
    """Rejecting a genuinely new subject is the worse failure: the audit and
    quality gates get another look at an admitted draft, but a rejected one is
    simply gone."""
    verdict = judge_relevance(_evidence(nearest_similarity=0.2))

    assert verdict.accepted is True


# --- credibility signals (ADR 0001) --------------------------------------


def test_absent_credibility_signals_are_neutral_never_a_penalty():
    """The criterion most likely to be got wrong, and getting it wrong rejects
    the entire existing corpus and every hand-dropped note — none of which
    carry signals."""
    without = judge_relevance(_evidence(has_credibility_signals=False))
    with_signals = judge_relevance(_evidence(has_credibility_signals=True))

    assert without.accepted is True
    assert with_signals.accepted is True


def test_a_concept_with_no_signals_at_all_is_still_accepted():
    """The all-`None` source case, spelled out: every existing concept in this
    vault predates signal capture."""
    verdict = judge_relevance(
        RelevanceEvidence(
            bundle_size=ESTABLISHED,
            nearest_similarity=0.5,
            has_credibility_signals=False,
        )
    )

    assert verdict.accepted is True


def test_signals_can_only_help_a_marginal_draft_never_hurt_it():
    marginal = 0.12  # below the base floor, above the relaxed one

    assert judge_relevance(_evidence(nearest_similarity=marginal)).accepted is False
    assert (
        judge_relevance(
            _evidence(nearest_similarity=marginal, has_credibility_signals=True)
        ).accepted
        is True
    )


def test_signals_do_not_rescue_a_redundant_draft():
    """Credibility says nothing about whether the bundle already has it."""
    verdict = judge_relevance(
        _evidence(nearest_similarity=0.99, has_credibility_signals=True)
    )

    assert verdict.accepted is False


# --- unknown is not a reason to reject -----------------------------------


def test_an_unknown_similarity_is_accepted_rather_than_treated_as_zero():
    """No candidates found is not the same as "unrelated to everything"."""
    verdict = judge_relevance(_evidence(nearest_similarity=None))

    assert verdict.accepted is True
    assert "unknown" in verdict.reason


def test_an_empty_bundle_accepts_everything():
    verdict = judge_relevance(RelevanceEvidence(bundle_size=0))

    assert verdict.accepted is True


# --- what the verdict carries --------------------------------------------


def test_the_verdict_carries_a_score_for_the_log_but_nothing_persists_it():
    """§5.1 refuses to store a credibility number because it starts going
    stale immediately. The score exists to explain one decision, and the
    verdict is discarded with it — nothing here reaches frontmatter."""
    verdict = judge_relevance(_evidence(nearest_similarity=0.42))

    assert verdict.score == 0.42
    assert set(vars(verdict)) == {"accepted", "reason", "score"}


def test_every_rejection_explains_itself():
    """The rationale is all that survives a rejected draft, so it has to be
    enough for a human to disagree with."""
    rejections = [
        judge_relevance(_evidence(nearest_similarity=0.99, nearest_concept_id="x")),
        judge_relevance(_evidence(nearest_similarity=0.0)),
    ]

    for verdict in rejections:
        assert verdict.accepted is False
        assert len(verdict.reason) > 20

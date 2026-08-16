"""The LLM-backed assessment adapter.

Everything here is about surviving what small local models actually return:
fenced JSON, leaked reasoning, a missing rubric, a score of "3". #12 measured
how unreliable that output is, so tolerance is a requirement rather than
defensive habit.
"""

from __future__ import annotations

import pytest

from tutor.adapters.llm import assessment as module
from tutor.adapters.llm.assessment import LiteLlmAssessmentSkill
from tutor.application.ports.outbound.assessment import Assessment
from tutor.application.ports.outbound.vault import Concept
from tutor.domain.assessment import Rubric, RubricContent, aggregate_scores, rating_for
from tutor.domain.depth import DepthLevel
from tutor.domain.scheduling import Rating

CONCEPT = Concept(
    concept_id="attention",
    title="Attention",
    body="Attention weights every token against every other.",
)

ASSESSMENT = Assessment(
    concept_id="attention",
    question="What does attention do?",
    rubrics=[
        Rubric("mechanism", RubricContent("Names the weighting.")),
        Rubric("limits", RubricContent("Says where it is expensive.")),
    ],
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def reply(monkeypatch):
    """Puts one canned model reply in front of the adapter, and records the
    prompt it was given."""
    sent: list[str] = []

    def _set(content: str):
        async def _acompletion(**kwargs):
            sent.append(kwargs["messages"][0]["content"])
            return {"choices": [{"message": {"content": content}}]}

        monkeypatch.setattr(module, "acompletion", _acompletion)
        return sent

    return _set


def _skill() -> LiteLlmAssessmentSkill:
    return LiteLlmAssessmentSkill("ollama_chat/qwen3.5:4b", "http://localhost:11434")


# --- generating -----------------------------------------------------------


@pytest.mark.anyio
async def test_a_well_formed_reply_becomes_an_assessment(reply):
    reply(
        '{"question": "How does attention weight tokens?",'
        ' "rubrics": [{"rubric_id": "mechanism", "criterion": "Names the weighting."}]}'
    )

    result = await _skill().generate(CONCEPT, DepthLevel.WORKING)

    assert result.question == "How does attention weight tokens?"
    assert result.rubrics[0].rubric_content.text_property == "Names the weighting."
    assert result.concept_id == "attention"


@pytest.mark.anyio
async def test_the_concepts_own_content_is_what_the_question_is_grounded_in(reply):
    sent = reply('{"question": "q", "rubrics": [{"criterion": "c"}]}')

    await _skill().generate(CONCEPT, DepthLevel.AWARE)

    assert "Attention weights every token against every other." in sent[0]


@pytest.mark.anyio
async def test_the_depth_level_changes_what_is_asked_for(reply):
    sent = reply('{"question": "q", "rubrics": [{"criterion": "c"}]}')

    await _skill().generate(CONCEPT, DepthLevel.SPECIALIST)
    await _skill().generate(CONCEPT, DepthLevel.AWARE)

    assert "in their own words" in sent[0]
    assert "Recognising it" in sent[1]


@pytest.mark.anyio
async def test_fenced_json_is_read(reply):
    """Small models fence their output whatever the prompt says."""
    reply('Sure!\n```json\n{"question": "q", "rubrics": [{"criterion": "c"}]}\n```')

    assert (await _skill().generate(CONCEPT, DepthLevel.AWARE)).question == "q"


@pytest.mark.anyio
async def test_leaked_reasoning_before_the_json_is_read(reply):
    """`qwen3.5:4b` leaks reasoning into its reply (#12)."""
    reply('Wait, I should think about this. {"question": "q", "rubrics": [{"criterion": "c"}]}')

    assert (await _skill().generate(CONCEPT, DepthLevel.AWARE)).question == "q"


@pytest.mark.anyio
async def test_an_unusable_reply_still_produces_a_question(reply):
    """A review the learner cannot be asked is a session that stops. The
    fallback is a poor question and says so, so a run of them is visible in the
    log rather than passing as ordinary reviews."""
    reply("I'm not sure what you want.")

    result = await _skill().generate(CONCEPT, DepthLevel.AWARE)

    assert "Attention" in result.question
    assert result.rubrics[0].rubric_id == "fallback-substance"


@pytest.mark.anyio
async def test_a_reply_with_no_rubrics_is_unusable(reply):
    """A question with nothing to grade it against cannot produce a rating."""
    reply('{"question": "a fine question", "rubrics": []}')

    assert (await _skill().generate(CONCEPT, DepthLevel.AWARE)).rubrics[
        0
    ].rubric_id == "fallback-substance"


# --- grading --------------------------------------------------------------


@pytest.mark.anyio
async def test_grading_returns_one_score_per_rubric_and_no_verdict(reply):
    reply(
        '[{"rubric_id": "mechanism", "score": 1.0, "rationale": "exact"},'
        ' {"rubric_id": "limits", "score": 0.5}]'
    )

    scores = await _skill().grade(ASSESSMENT, "it weights tokens")

    assert [s.rubric_id for s in scores] == ["mechanism", "limits"]
    assert [s.score for s in scores] == [1.0, 0.5]
    assert not hasattr(scores[0], "rating")


@pytest.mark.anyio
async def test_a_rubric_the_grader_skipped_is_unjudged_not_zero(reply):
    """The rollup drops it; a zero would let the grader's silence become the
    learner's failure."""
    reply('[{"rubric_id": "mechanism", "score": 1.0}]')

    scores = await _skill().grade(ASSESSMENT, "an answer")

    assert scores[1].score is None
    assert rating_for(aggregate_scores(scores)) is Rating.EASY


@pytest.mark.anyio
async def test_a_null_score_is_passed_through_as_unjudged(reply):
    reply('[{"rubric_id": "mechanism", "score": null, "rationale": "cannot tell"}]')

    scores = await _skill().grade(ASSESSMENT, "an answer")

    assert scores[0].score is None
    assert scores[0].rationale == "cannot tell"


@pytest.mark.anyio
async def test_an_out_of_range_score_is_clamped(reply):
    reply('[{"rubric_id": "mechanism", "score": 3.0}, {"rubric_id": "limits", "score": -1}]')

    scores = await _skill().grade(ASSESSMENT, "an answer")

    assert [s.score for s in scores] == [1.0, 0.0]


@pytest.mark.anyio
async def test_a_non_numeric_score_is_unjudged_rather_than_guessed(reply):
    """"good" is a malformed answer, not a perfect one."""
    reply('[{"rubric_id": "mechanism", "score": "good"}]')

    assert (await _skill().grade(ASSESSMENT, "an answer"))[0].score is None


@pytest.mark.anyio
async def test_a_single_rubric_returned_as_a_bare_object_is_read(reply):
    """A grader scoring exactly one rubric sometimes drops the array."""
    reply('{"rubric_id": "mechanism", "score": 0.8}')

    assert (await _skill().grade(ASSESSMENT, "an answer"))[0].score == 0.8


@pytest.mark.anyio
async def test_an_unparseable_grading_leaves_everything_unjudged(reply):
    """Which makes the rollup `graded=False`, and `rating_for` refuses — the
    review is not written rather than recorded as a lapse."""
    reply("I could not grade that.")

    scores = await _skill().grade(ASSESSMENT, "an answer")

    assert all(score.score is None for score in scores)
    assert not aggregate_scores(scores).graded

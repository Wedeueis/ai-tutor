"""`LiteLlmDiscoverySkill` — turning a model's prose into `Discovery` values.

The load-bearing test here is `test_an_unknown_kind_is_dropped_not_defaulted`.
Everything else in this file is ordinary tolerance for small local models
(#12); that one is the memory boundary. A model that invents
`"kind": "learner_blindspot"` must produce nothing, and it must not produce a
proposal — a default branch would route the one thing that may never leave
`tutor` into the vault (§2.1, NFR5).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from tutor.adapters.llm.discovery import LiteLlmDiscoverySkill
from tutor.application.ports.outbound.discovery import DiscoveryKind

TAUGHT = ("concepts/spaced-repetition", "concepts/cold-brew-coffee")

TRANSCRIPT = "learner: what is ease factor?\n\ntutor: the vault never says."


@pytest.fixture
def anyio_backend():
    return "asyncio"


def responding(content: str):
    """Patches the one LiteLLM call this adapter makes."""

    async def _completion(**kwargs):
        return {"choices": [{"message": {"content": content}}]}

    return patch("tutor.adapters.llm.discovery.acompletion", _completion)


async def discover(content: str, transcript: str = TRANSCRIPT):
    with responding(content):
        return await LiteLlmDiscoverySkill("m").discover(transcript, TAUGHT)


# --- the boundary ---------------------------------------------------------


@pytest.mark.anyio
async def test_an_unknown_kind_is_dropped_not_defaulted():
    """A blindspot has no `DiscoveryKind`, so a model claiming one produces
    nothing at all — not a proposal, not an inquiry."""
    found = await discover(
        '[{"kind": "learner_blindspot", "title": "confuses X with Y",'
        ' "body": "they keep mixing them up"}]'
    )

    assert found == []


@pytest.mark.anyio
async def test_a_valid_kind_alongside_an_invalid_one_still_survives():
    found = await discover(
        '[{"kind": "learner_blindspot", "title": "a", "body": "b"},'
        ' {"kind": "coverage_gap", "title": "ease factor undefined", "body": "b"}]'
    )

    assert [d.kind for d in found] == [DiscoveryKind.COVERAGE_GAP]


# --- parsing tolerance ----------------------------------------------------


@pytest.mark.anyio
async def test_it_reads_all_three_kinds():
    found = await discover(
        '[{"kind": "coverage_gap", "title": "a", "body": "b"},'
        ' {"kind": "contradiction", "title": "c", "body": "d"},'
        ' {"kind": "derived_concept", "title": "e", "body": "f"}]'
    )

    assert [d.kind for d in found] == list(DiscoveryKind)


@pytest.mark.anyio
async def test_a_fenced_array_is_read():
    found = await discover(
        'Here is what I found:\n```json\n[{"kind": "coverage_gap",'
        ' "title": "a", "body": "b"}]\n```\nHope that helps.'
    )

    assert len(found) == 1


@pytest.mark.anyio
async def test_unusable_output_is_no_discoveries_rather_than_an_error():
    assert await discover("I could not find anything useful.") == []


@pytest.mark.anyio
async def test_an_empty_array_is_respected():
    """A session that revealed nothing is the common case, not a failure."""
    assert await discover("[]") == []


@pytest.mark.anyio
async def test_an_entry_without_a_body_is_dropped():
    """A title with nothing behind it is not a finding anyone can act on."""
    assert await discover('[{"kind": "coverage_gap", "title": "a", "body": ""}]') == []


@pytest.mark.anyio
async def test_kind_is_read_case_insensitively():
    found = await discover('[{"kind": "Coverage_Gap", "title": "a", "body": "b"}]')

    assert [d.kind for d in found] == [DiscoveryKind.COVERAGE_GAP]


# --- concept ids ----------------------------------------------------------


@pytest.mark.anyio
async def test_concept_ids_are_narrowed_to_what_was_taught():
    """A model naming a concept that was not in this session is guessing, and a
    link to a concept that does not exist is worse than no link."""
    found = await discover(
        '[{"kind": "coverage_gap", "title": "a", "body": "b", "concept_ids":'
        ' ["concepts/spaced-repetition", "concepts/invented"]}]'
    )

    assert found[0].concept_ids == ("concepts/spaced-repetition",)


@pytest.mark.anyio
async def test_missing_concept_ids_are_empty_not_an_error():
    found = await discover('[{"kind": "contradiction", "title": "a", "body": "b"}]')

    assert found[0].concept_ids == ()


# --- when the model is not called at all ----------------------------------


@pytest.mark.anyio
async def test_an_empty_transcript_never_reaches_the_model():
    """Asking a model to find findings in no text is how you get invented
    ones. The session store is disposable and may hand back nothing (#39)."""
    called = False

    async def _completion(**kwargs):
        nonlocal called
        called = True
        return {"choices": [{"message": {"content": "[]"}}]}

    with patch("tutor.adapters.llm.discovery.acompletion", _completion):
        found = await LiteLlmDiscoverySkill("m").discover("   \n  ", TAUGHT)

    assert found == []
    assert called is False

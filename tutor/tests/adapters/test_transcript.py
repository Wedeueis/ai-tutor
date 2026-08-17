"""`AdkTranscript` — the only reader of ADK's session store in all of `tutor`.

The store is disposable (#39), so the interesting cases are the degraded ones:
a session that is gone, events with no text, a transcript longer than the
prompt can hold. Each has a defined answer that is not an exception, because
the pass above this treats an empty transcript as nothing to report.

ADK objects are faked with plain namespaces rather than constructed for real:
what is being asserted is how this adapter walks `session.events[*].content
.parts[*].text`, and ADK's own types would only make the shape harder to see.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tutor.adapters.adk.transcript import MAX_TRANSCRIPT_CHARS, AdkTranscript


@pytest.fixture
def anyio_backend():
    return "asyncio"


def event(role: str, *texts: str) -> SimpleNamespace:
    return SimpleNamespace(
        content=SimpleNamespace(
            role=role, parts=[SimpleNamespace(text=text) for text in texts]
        )
    )


class FakeSessionService:
    def __init__(self, session=None) -> None:
        self.session = session
        self.calls: list[dict] = []

    async def get_session(self, **kwargs):
        self.calls.append(kwargs)
        return self.session


@pytest.mark.anyio
async def test_it_renders_both_sides_of_the_exchange():
    service = FakeSessionService(
        SimpleNamespace(
            events=[event("user", "what is FSRS?"), event("model", "a scheduler.")]
        )
    )

    rendered = await AdkTranscript(service).read("s1")

    assert rendered == "learner: what is FSRS?\n\ntutor: a scheduler."


@pytest.mark.anyio
async def test_any_non_user_role_is_the_tutor():
    """The learner is the one identifiable speaker; everything else in the
    stream is the system talking."""
    service = FakeSessionService(SimpleNamespace(events=[event("assistant", "hello")]))

    assert (await AdkTranscript(service).read("s1")).startswith("tutor: ")


@pytest.mark.anyio
async def test_multi_part_events_are_joined():
    service = FakeSessionService(
        SimpleNamespace(events=[event("user", "one ", "two")])
    )

    assert await AdkTranscript(service).read("s1") == "learner: one two"


@pytest.mark.anyio
async def test_events_with_no_text_are_skipped():
    """Tool calls and empty parts carry no dialogue — a blank turn in the
    transcript is noise the model would try to interpret."""
    service = FakeSessionService(
        SimpleNamespace(
            events=[
                event("user", ""),
                SimpleNamespace(content=None),
                event("model", "real text"),
            ]
        )
    )

    assert await AdkTranscript(service).read("s1") == "tutor: real text"


@pytest.mark.anyio
async def test_a_missing_session_is_empty_not_an_error():
    """The store may simply be gone (#39). The pass above reads this as
    nothing to report."""
    assert await AdkTranscript(FakeSessionService(None)).read("s1") == ""


@pytest.mark.anyio
async def test_a_session_with_no_events_is_empty():
    assert await AdkTranscript(FakeSessionService(SimpleNamespace(events=[]))).read("s1") == ""


@pytest.mark.anyio
async def test_truncation_keeps_the_end():
    """The later exchanges are where a contradiction has usually surfaced and
    where the tutor has already said the vault is thin on something."""
    service = FakeSessionService(
        SimpleNamespace(events=[event("user", "old " * 200), event("model", "THE END")])
    )

    rendered = await AdkTranscript(service, max_chars=40).read("s1")

    assert len(rendered) == 40
    assert rendered.endswith("THE END")


@pytest.mark.anyio
async def test_a_short_transcript_is_not_truncated():
    service = FakeSessionService(SimpleNamespace(events=[event("user", "short")]))

    assert await AdkTranscript(service).read("s1") == "learner: short"


@pytest.mark.anyio
async def test_it_asks_for_the_session_it_was_given():
    service = FakeSessionService(SimpleNamespace(events=[]))

    await AdkTranscript(service, app_name="tutor", user_id="learner").read("s-42")

    assert service.calls == [
        {"app_name": "tutor", "user_id": "learner", "session_id": "s-42"}
    ]


def test_the_default_budget_leaves_room_for_the_concepts():
    """A long session against a small local context window would otherwise push
    the concepts out of the prompt entirely."""
    assert 0 < MAX_TRANSCRIPT_CHARS <= 32_000

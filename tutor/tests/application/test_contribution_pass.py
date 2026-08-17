"""The pass that runs after a session ends.

Two properties carry the weight here, in the order they matter:

1. **A failure must not cost a review.** Losing an inquiry is survivable;
   losing a review event is not, because it cannot be regenerated. So the
   tests care less about the happy path than about what a broken model,
   a broken transcript and a broken write each do to everything around them.
2. **Nothing about the learner can be emitted** — and not by filtering. There
   is no `DiscoveryKind` for it and no `ContributionPort` verb that takes one
   (§2.1, NFR5).

The contributions adapter is real rather than faked: what is being asserted is
that a gap ends up in the inbox and a proposal does not, and a fake would just
restate the routing table the pass already declares.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest

from tutor.adapters.filesystem.contributions import FilesystemContributions
from tutor.application.contributions import ContributionPass
from tutor.application.ports.outbound.discovery import (
    Discovery,
    DiscoveryKind,
)
from tutor.application.teaching import SessionReport
from tutor.domain.review import ReviewEvent
from tutor.domain.scheduling import ALGORITHM, PARAMETERS_ID, Rating

TAUGHT = ("concepts/spaced-repetition", "concepts/cold-brew-coffee")

REVIEWED = ReviewEvent(
    concept_id="concepts/spaced-repetition",
    rating=Rating.GOOD,
    reviewed_at=datetime(2026, 8, 16, 9, 0, tzinfo=UTC),
    algorithm=ALGORITHM,
    parameters=PARAMETERS_ID,
    question="What is spaced repetition for?",
    rubric="Names the forgetting curve.",
    answer="Reviewing just before you would forget.",
    grade="0.9",
)

GAP = Discovery(
    kind=DiscoveryKind.COVERAGE_GAP,
    title="Ease factor is used but never defined",
    body="Three concepts lean on *ease factor* and none says what it is.",
    concept_ids=("concepts/spaced-repetition",),
)

CONTRADICTION = Discovery(
    kind=DiscoveryKind.CONTRADICTION,
    title="Cold brew steeping time disagrees",
    body="One concept says 12-24h, the other says 8h.",
    concept_ids=TAUGHT,
)

DERIVED = Discovery(
    kind=DiscoveryKind.DERIVED_CONCEPT,
    title="Retrieval practice versus rereading",
    body="Both describe the same effect from different angles.",
    concept_ids=("concepts/spaced-repetition",),
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def dirs(tmp_path):
    return tmp_path / "vault" / "raw" / "inquiries", tmp_path / "proposals"


@pytest.fixture
def contributions(dirs):
    return FilesystemContributions(*dirs)


class FakeTranscript:
    def __init__(self, text: str = "learner: hi\n\ntutor: hello", raises=None) -> None:
        self.text = text
        self.raises = raises
        self.calls: list[str] = []

    async def read(self, session_id: str) -> str:
        self.calls.append(session_id)
        if self.raises is not None:
            raise self.raises
        return self.text


class FakeDiscoveries:
    def __init__(self, discoveries=(), raises=None) -> None:
        self.discoveries = list(discoveries)
        self.raises = raises
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    async def discover(self, transcript, concept_ids):
        self.calls.append((transcript, concept_ids))
        if self.raises is not None:
            raise self.raises
        return list(self.discoveries)


def report(*, concept_ids=TAUGHT, reviewed=()) -> SessionReport:
    return SessionReport(reviewed=tuple(reviewed), concept_ids=tuple(concept_ids))


def make(contributions, discoveries, transcript=None) -> ContributionPass:
    return ContributionPass(transcript or FakeTranscript(), discoveries, contributions)


# --- routing: what goes where ---------------------------------------------


@pytest.mark.anyio
async def test_a_coverage_gap_lands_in_the_inbox(contributions, dirs):
    """Automatic, no approval step — an inquiry creates no knowledge, it asks
    for some (§2.1)."""
    inquiries, _ = dirs
    written = await make(contributions, FakeDiscoveries([GAP])).run("s1", report())

    assert [path.parent for path in written] == [inquiries]
    assert "ease factor" in written[0].read_text().lower()


@pytest.mark.anyio
async def test_a_contradiction_also_lands_in_the_inbox(contributions, dirs):
    inquiries, _ = dirs
    written = await make(contributions, FakeDiscoveries([CONTRADICTION])).run(
        "s1", report()
    )

    assert written[0].parent == inquiries


@pytest.mark.anyio
async def test_a_derived_concept_waits_outside_the_vault(contributions, dirs):
    """`pipeline` remains the only thing that ever creates a concept; approving
    this is a person moving the file into `vault/raw/` (§2.1)."""
    inquiries, proposals = dirs
    written = await make(contributions, FakeDiscoveries([DERIVED])).run("s1", report())

    assert written[0].parent == proposals
    assert written[0].parent != inquiries
    assert "Awaiting human approval" in written[0].read_text()


@pytest.mark.anyio
async def test_every_discovery_kind_is_routed(contributions):
    """Exhaustive over `DiscoveryKind` on purpose: a new kind must not be
    addable without deciding where it goes."""
    discoveries = [
        Discovery(kind=kind, title=f"t {kind.value}", body="b") for kind in DiscoveryKind
    ]
    written = await make(contributions, FakeDiscoveries(discoveries)).run("s1", report())

    assert len(written) == len(DiscoveryKind)


# --- it must never cost a review ------------------------------------------


@pytest.mark.anyio
async def test_a_failing_model_loses_inquiries_and_nothing_else(contributions):
    """Every review was already committed as it happened. The right thing to
    lose here is the inquiries (#39)."""
    finished = report(reviewed=(REVIEWED,))

    written = await make(
        contributions, FakeDiscoveries(raises=RuntimeError("model is down"))
    ).run("s1", finished)

    assert written == []
    assert finished.reviewed == (REVIEWED,)


@pytest.mark.anyio
async def test_an_unreadable_transcript_does_not_raise(contributions):
    """The ADK session store is disposable (#39) — it may simply be gone."""
    transcript = FakeTranscript(raises=RuntimeError("session store is gone"))

    written = await make(contributions, FakeDiscoveries([GAP]), transcript).run(
        "s1", report()
    )

    assert written == []


@pytest.mark.anyio
async def test_one_bad_discovery_does_not_lose_the_others(contributions, dirs):
    inquiries, _ = dirs
    # Break the write rather than the discovery: a title that slugifies to
    # nothing still writes (as `untitled`), so the only way to fail one of two
    # files is a directory the adapter cannot create.
    broken = FilesystemContributions(inquiries / "x\0y", dirs[1])
    written = await make(broken, FakeDiscoveries([GAP, DERIVED])).run("s1", report())

    # The gap's write fails; the proposal's does not.
    assert len(written) == 1
    assert written[0].parent == dirs[1]


# --- when it does not run at all ------------------------------------------


@pytest.mark.anyio
async def test_a_session_that_taught_nothing_never_reaches_the_model(contributions):
    discoveries = FakeDiscoveries([GAP])

    written = await make(contributions, discoveries).run("s1", report(concept_ids=()))

    assert written == []
    assert discoveries.calls == []


@pytest.mark.anyio
async def test_it_reads_the_session_it_was_given(contributions):
    """It runs while the transcript is live, against *this* session — not as a
    nightly job over old ones (#43)."""
    transcript = FakeTranscript()
    discoveries = FakeDiscoveries([])

    await make(contributions, discoveries, transcript).run("s-42", report())

    assert transcript.calls == ["s-42"]
    assert discoveries.calls[0][1] == TAUGHT


# --- the boundary ---------------------------------------------------------


def test_there_is_no_discovery_kind_for_the_learner():
    """The enforcement is the enumeration (§2.1, NFR5). A blindspot cannot be
    expressed, so nothing downstream has to decide whether it is safe to file."""
    assert {kind.value for kind in DiscoveryKind} == {
        "coverage_gap",
        "contradiction",
        "derived_concept",
    }


def test_the_pass_routes_only_through_the_two_verbs():
    """`ContributionPass` must not acquire a way to write that bypasses the
    port — the source names `record_inquiry` and `propose_concept` and nothing
    else that writes."""
    source = inspect.getsource(ContributionPass)

    assert "record_inquiry" in source
    assert "propose_concept" in source
    assert "open(" not in source
    assert "write_text" not in source

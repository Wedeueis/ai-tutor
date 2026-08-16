"""What `tutor` may send outward, and what it may not.

NFR5 calls the semantic/episodic boundary the constraint most likely to be
violated by a well-meaning later feature, so the tests here are less about
whether files land in the right folder and more about whether there *is* a way
to put the wrong thing in one.
"""

from __future__ import annotations

import inspect
from datetime import date

import pytest

from tutor.adapters.filesystem.contributions import (
    FilesystemContributions,
    OutsideTheAllowedRoots,
)
from tutor.application.ports.outbound.contributions import ContributionPort
from tutor.domain.contribution import (
    ORIGIN_MARKER,
    Inquiry,
    InquiryKind,
    Proposal,
    slugify,
)

ON = date(2026, 8, 16)

GAP = Inquiry(
    kind=InquiryKind.COVERAGE_GAP,
    title="Ease factor is used but never defined",
    body="Three concepts lean on *ease factor* and none of them says what it is.",
    concept_ids=("concepts/spaced-repetition",),
)

CONTRADICTION = Inquiry(
    kind=InquiryKind.CONTRADICTION,
    title="Cold brew steeping time disagrees",
    body="`cold-brew-coffee` says 12–24h; `cold-brew-concentrate-ratio` says 8h.",
    concept_ids=("concepts/cold-brew-coffee", "concepts/cold-brew-concentrate-ratio"),
)

PROPOSAL = Proposal(
    title="Retrieval practice versus rereading",
    body="Both concepts describe the same effect from different angles.",
    concept_ids=("concepts/retrieval-practice",),
)


@pytest.fixture
def dirs(tmp_path):
    return tmp_path / "vault" / "raw" / "inquiries", tmp_path / "proposals"


@pytest.fixture
def contributions(dirs):
    return FilesystemContributions(*dirs)


# --- the boundary is what the port lacks ----------------------------------


def test_the_port_has_exactly_two_verbs():
    """The enforcement (§2.1, NFR5). A guard that inspects content and decides
    can be wrong; a verb that does not exist cannot be called."""
    verbs = {
        name
        for name, _ in inspect.getmembers(ContributionPort, inspect.isfunction)
        if not name.startswith("_")
    }

    assert verbs == {"record_inquiry", "propose_concept"}


def test_there_is_no_way_to_file_anything_about_the_learner():
    """"You keep confusing X with Y" is a reading of the review log. It means
    nothing to anyone who was not there, and there is no type for it — a later
    feature wanting to file one has to add a method someone reviews."""
    import tutor.domain.contribution as contribution

    exported = {name.lower() for name in dir(contribution)}

    assert not {name for name in exported if "blindspot" in name or "learner" in name}


def test_neither_verb_takes_a_destination(contributions):
    """Both directories are fixed when the adapter is constructed. A path
    argument would make the boundary a matter of what the caller passed."""
    for verb in (contributions.record_inquiry, contributions.propose_concept):
        parameters = set(inspect.signature(verb).parameters)
        assert len(parameters) == 1


# --- inquiries: automatic, to the inbox -----------------------------------


def test_a_coverage_gap_lands_in_the_inbox(contributions, dirs):
    inquiries, _ = dirs

    path = contributions.record_inquiry(GAP)

    assert path.parent == inquiries.resolve()
    assert "Ease factor" in path.read_text()


def test_a_contradiction_names_both_concepts(contributions):
    """For a contradiction the concepts *are* the content — a note saying two
    things disagree without saying which two is unusable."""
    text = contributions.record_inquiry(CONTRADICTION).read_text()

    assert "/concepts/cold-brew-coffee.md" in text
    assert "/concepts/cold-brew-concentrate-ratio.md" in text


def test_an_inquiry_carries_no_frontmatter(contributions):
    """`vault/raw/` is a capture surface, not the bundle (CLAUDE.md).
    Frontmatter would make it look like a concept, and `tutor` never writes the
    bundle (#8)."""
    text = contributions.record_inquiry(GAP).read_text()

    assert not text.startswith("---")
    assert "type:" not in text


def test_an_inquiry_says_it_came_from_the_tutor(contributions):
    text = contributions.record_inquiry(GAP).read_text()

    assert f"`{ORIGIN_MARKER}`" in text
    assert "not knowledge and not captured material" in text


# --- proposals: not automatic ---------------------------------------------


def test_a_proposal_waits_outside_the_vault(contributions, dirs):
    """`pipeline` remains the only thing that ever creates a concept, so a
    derived concept does not get to walk into the inbox on its own."""
    inquiries, proposals = dirs

    path = contributions.propose_concept(PROPOSAL)

    assert path.parent == proposals.resolve()
    assert not inquiries.exists()


def test_a_proposal_says_how_to_approve_it(contributions):
    """Approval is `mv`. The file says so, because nothing else will."""
    text = contributions.propose_concept(PROPOSAL).read_text()

    assert "Awaiting human approval" in text
    assert "`vault/raw/`" in text


def test_a_proposal_is_shaped_like_raw_material(contributions):
    """Approving it means moving it into `vault/raw/`, so it has to already be
    the shape of something that belongs there: plain markdown, no frontmatter."""
    text = contributions.propose_concept(PROPOSAL).read_text()

    assert not text.startswith("---")


# --- the filename convention ----------------------------------------------


def test_the_filename_is_dated_attributed_and_typed_in_that_order():
    """The order someone scanning a directory listing needs them in."""
    assert GAP.filename(ON) == "2026-08-16-tutor-gap-ease-factor-is-used-but-never-defined.md"
    assert CONTRADICTION.filename(ON).startswith("2026-08-16-tutor-contradiction-")
    assert PROPOSAL.filename(ON).startswith("2026-08-16-tutor-concept-")


def test_tutor_origin_is_legible_before_anyone_opens_the_file():
    """`vault/raw/` is mostly PDFs and notes the user dropped there on purpose.
    Something that appeared on its own should say so in its own name."""
    assert ORIGIN_MARKER in GAP.filename(ON)


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Ratio: 1/8 — really?", "ratio-1-8-really"),
        ("  spaced   out  ", "spaced-out"),
        ("../../etc/passwd", "etc-passwd"),
        ("!!!", "untitled"),
        ("x" * 200, "x" * 60),
    ],
)
def test_slugs_are_safe_path_segments(title, expected):
    """Everything outside `[a-z0-9-]` goes, which removes every way a title
    could climb out of its directory."""
    assert slugify(title) == expected


# --- never overwrite ------------------------------------------------------


def test_a_second_inquiry_about_the_same_thing_gets_its_own_file(contributions):
    """The inbox is somebody's capture surface. Replacing a note they may
    already have started editing is a far worse failure than a duplicate."""
    first = contributions.record_inquiry(GAP)
    second = contributions.record_inquiry(GAP)

    assert first != second
    assert second.name.endswith("-2.md")
    assert first.exists() and second.exists()


def test_writing_outside_the_allowed_root_is_refused(dirs, monkeypatch):
    """Unreachable through `slugify` — which is why it is checked. This is the
    one component that can touch the user's vault."""
    inquiries, proposals = dirs
    contributions = FilesystemContributions(inquiries, proposals)
    monkeypatch.setattr(
        Inquiry, "filename", lambda self, on: "../../escaped.md", raising=True
    )

    with pytest.raises(OutsideTheAllowedRoots):
        contributions.record_inquiry(GAP)


def test_the_directories_are_created_on_first_write(contributions, dirs):
    inquiries, _ = dirs
    assert not inquiries.exists()

    contributions.record_inquiry(GAP)

    assert inquiries.is_dir()

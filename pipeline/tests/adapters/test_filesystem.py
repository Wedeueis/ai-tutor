from datetime import datetime

from pipeline.adapters.filesystem.markdown_concept_repository import MarkdownConceptRepository
from pipeline.domain.concept import (
    Actor,
    Concept,
    ConceptId,
    Frontmatter,
    Generated,
    Source,
    VerificationEvent,
)
from pipeline.domain.eval import EvalResult, RubricScore


def test_save_then_load_round_trips(tmp_path):
    repo = MarkdownConceptRepository(tmp_path)
    concept = Concept(
        id=ConceptId("coffee/espresso"),
        frontmatter=Frontmatter(
            type="Playbook",
            title="Espresso Ratio",
            tags=["coffee"],
            generated=Generated(by=Actor("human:wedeueis"), at=datetime(2026, 8, 9, 12, 0)),
            verified=[VerificationEvent(by=Actor("human:wedeueis"), at=datetime(2026, 8, 9, 12, 0))],
        ),
        body="Use a 1:2 ratio.",
    )

    repo.save(concept)
    loaded = repo.load(ConceptId("coffee/espresso"))

    assert loaded.frontmatter.type == "Playbook"
    assert loaded.frontmatter.title == "Espresso Ratio"
    assert loaded.frontmatter.tags == ["coffee"]
    assert loaded.frontmatter.generated.by.value == "human:wedeueis"
    assert loaded.body.strip() == "Use a 1:2 ratio."


def test_save_then_load_round_trips_domain_and_eval(tmp_path):
    repo = MarkdownConceptRepository(tmp_path)
    domain_concept = Concept(
        id=ConceptId("domains/coffee"), frontmatter=Frontmatter(type="Domain", title="Coffee"), body=""
    )
    repo.save(domain_concept)
    assert repo.load(ConceptId("domains/coffee")).frontmatter.title == "Coffee"

    eval_result = EvalResult(
        scores=[RubricScore("traceable", 0.4, "not grounded")],
        average_score=0.4,
        passed=False,
    )
    member = Concept(
        id=ConceptId("espresso"),
        frontmatter=Frontmatter(type="Playbook", domain=None, eval=eval_result),
        body="",
    )
    repo.save(member)
    loaded = repo.load(ConceptId("espresso"))
    assert loaded.frontmatter.domain is None
    assert loaded.frontmatter.eval.passed is False
    assert loaded.frontmatter.eval.scores[0].rubric_id == "traceable"


def test_list_skips_reserved_filenames_and_raw(tmp_path):
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "note.md").write_text("not a concept", encoding="utf-8")
    (tmp_path / "index.md").write_text("# index", encoding="utf-8")
    (tmp_path / "log.md").write_text("# log", encoding="utf-8")

    repo = MarkdownConceptRepository(tmp_path)
    repo.save(Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body=""))

    ids = {c.value for c in repo.list()}
    assert ids == {"a"}


def test_exists(tmp_path):
    repo = MarkdownConceptRepository(tmp_path)
    assert not repo.exists(ConceptId("a"))
    repo.save(Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body=""))
    assert repo.exists(ConceptId("a"))


def test_delete_removes_the_file(tmp_path):
    repo = MarkdownConceptRepository(tmp_path)
    repo.save(Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body=""))

    repo.delete(ConceptId("a"))

    assert not repo.exists(ConceptId("a"))


def test_delete_is_a_noop_when_concept_does_not_exist(tmp_path):
    repo = MarkdownConceptRepository(tmp_path)
    repo.delete(ConceptId("does-not-exist"))  # must not raise


def test_every_source_field_survives_a_round_trip(tmp_path):
    """`_sources_list` is an allow-list, not a passthrough: a key it does not
    name is silently dropped the next time the concept is saved. That is a
    data-loss bug nobody would see, so every field is pinned here rather than
    only the one that was added last."""
    repo = MarkdownConceptRepository(tmp_path)
    source = Source(
        resource="/references/the-book.md",
        id="the-book-p17",
        title="The Book",
        author="human:someone",
        usage_count=3,
        last_modified="2026-01-02",
        locator="passage 17",
    )
    repo.save(
        Concept(
            id=ConceptId("a/b"),
            frontmatter=Frontmatter(type="Playbook", sources=[source]),
            body="Prose.[^the-book-p17]",
        )
    )

    loaded = repo.load(ConceptId("a/b"))

    assert loaded.frontmatter.sources == [source]


def test_a_locator_survives_two_round_trips(tmp_path):
    """The drop would happen on *re-save*, not on first write — so one
    save/load is not enough to catch it."""
    repo = MarkdownConceptRepository(tmp_path)
    concept = Concept(
        id=ConceptId("a/b"),
        frontmatter=Frontmatter(
            type="Playbook",
            sources=[Source(resource="/references/x.md", id="x-p1", locator="p. 42")],
        ),
        body="Prose.",
    )
    repo.save(concept)

    repo.save(repo.load(ConceptId("a/b")))

    assert repo.load(ConceptId("a/b")).frontmatter.sources[0].locator == "p. 42"

from datetime import date, datetime

from pipeline.adapters.filesystem.markdown_bundle_log import MarkdownBundleLog
from pipeline.adapters.filesystem.markdown_concept_repository import MarkdownConceptRepository
from pipeline.domain.concept import (
    Actor,
    Concept,
    ConceptId,
    Frontmatter,
    Generated,
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


def test_bundle_log_appends_under_todays_heading(tmp_path):
    log_path = tmp_path / "log.md"
    log = MarkdownBundleLog(log_path, today_provider=lambda: date(2026, 8, 9))

    log.append("**Creation**: Added [A](a.md).")
    log.append("**Creation**: Added [B](b.md).")

    content = log_path.read_text(encoding="utf-8")
    assert content.count("## 2026-08-09") == 1
    assert "* **Creation**: Added [A](a.md)." in content
    assert "* **Creation**: Added [B](b.md)." in content


def test_bundle_log_adds_new_heading_for_new_day(tmp_path):
    log_path = tmp_path / "log.md"
    log_path.write_text("# Directory Update Log\n\n## 2026-08-08\n* old entry\n", encoding="utf-8")
    log = MarkdownBundleLog(log_path, today_provider=lambda: date(2026, 8, 9))

    log.append("**Creation**: Added [A](a.md).")

    content = log_path.read_text(encoding="utf-8")
    assert content.index("## 2026-08-09") < content.index("## 2026-08-08")

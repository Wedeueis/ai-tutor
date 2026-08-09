from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from pipeline.domain.conformance import ConformanceChecker


def _concept(**frontmatter_kwargs) -> Concept:
    return Concept(
        id=ConceptId("notes/example"),
        frontmatter=Frontmatter(type="Playbook", **frontmatter_kwargs),
        body="body",
    )


def test_valid_concept_is_conformant():
    report = ConformanceChecker().check(_concept())
    assert report.ok
    assert report.issues == []


def test_empty_type_fails():
    concept = Concept(
        id=ConceptId("notes/example"),
        frontmatter=Frontmatter(type=""),
        body="body",
    )
    report = ConformanceChecker().check(concept)
    assert not report.ok
    assert any(issue.field == "type" for issue in report.issues)


def test_unrecognized_status_fails():
    report = ConformanceChecker().check(_concept(status="in-review"))
    assert not report.ok
    assert any(issue.field == "status" for issue in report.issues)

from pipeline.application.use_cases.validate_concept import ValidateConcept
from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from tests.application.fakes import FakeSchemaRegistry


def test_conformant_concept_with_no_registered_schema_passes():
    concept = Concept(
        id=ConceptId("notes/x"), frontmatter=Frontmatter(type="Playbook"), body=""
    )
    result = ValidateConcept(FakeSchemaRegistry()).run(concept)
    assert result.ok


def test_non_conformant_concept_fails():
    concept = Concept(
        id=ConceptId("notes/x"), frontmatter=Frontmatter(type=""), body=""
    )
    result = ValidateConcept(FakeSchemaRegistry()).run(concept)
    assert not result.ok
    assert any(issue.field == "type" for issue in result.issues)


def test_schema_violation_fails():
    schema = {
        "type": "object",
        "required": ["description"],
        "properties": {"description": {"type": "string"}},
    }
    concept = Concept(
        id=ConceptId("notes/x"),
        frontmatter=Frontmatter(type="BigQuery Table"),
        body="",
    )
    result = ValidateConcept(
        FakeSchemaRegistry({"BigQuery Table": schema})
    ).run(concept)
    assert not result.ok
    assert any(issue.field == "schema" for issue in result.issues)


def test_schema_satisfied_passes():
    schema = {
        "type": "object",
        "required": ["description"],
        "properties": {"description": {"type": "string"}},
    }
    concept = Concept(
        id=ConceptId("notes/x"),
        frontmatter=Frontmatter(type="BigQuery Table", description="a table"),
        body="",
    )
    result = ValidateConcept(
        FakeSchemaRegistry({"BigQuery Table": schema})
    ).run(concept)
    assert result.ok

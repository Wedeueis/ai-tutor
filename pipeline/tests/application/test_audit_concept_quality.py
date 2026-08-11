from pipeline.application.use_cases.audit_concept_quality import AuditConceptQuality
from pipeline.domain.agent import QualityAuditVerdict
from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from tests.application.fakes import FakeConceptRepository, FakeQualityAuditSkill

GOOD_BODY = (
    "The Adam optimizer is a popular stochastic gradient descent optimizer "
    "that adapts the learning rate for each parameter."
)
GARBLED_BODY = (
    "|      |      |      | 6.11 | 23.7 | 36 |\n"
    "|      | 4    |      | 5.19 | 25.3 | 50 |\n"
    "|      | 8    |      | 4.88 | 25.5 | 80 |\n"
)


def _repo(concepts):
    repo = FakeConceptRepository()
    for concept in concepts:
        repo.save(concept)
    return repo


def test_garbled_concept_is_flagged_without_calling_the_skill():
    concept = Concept(
        id=ConceptId("garbled"), frontmatter=Frontmatter(type="Metric"), body=GARBLED_BODY
    )
    repo = _repo([concept])
    audit_skill = FakeQualityAuditSkill(
        {"garbled": QualityAuditVerdict(standalone_quality=True)}  # would say "fine" if asked
    )

    flags = AuditConceptQuality(repo, audit_skill).run()

    assert len(flags) == 1
    assert flags[0].concept_id == ConceptId("garbled")
    assert "garbled table" in flags[0].reason


def test_skill_flags_vacuous_but_grammatical_concept():
    concept = Concept(
        id=ConceptId("vacuous"),
        frontmatter=Frontmatter(type="Metric"),
        body="The following table represents a collection of data points.",
    )
    repo = _repo([concept])
    audit_skill = FakeQualityAuditSkill(
        {"vacuous": QualityAuditVerdict(standalone_quality=False, reason="just describes a table")}
    )

    flags = AuditConceptQuality(repo, audit_skill).run()

    assert len(flags) == 1
    assert flags[0].reason == "just describes a table"


def test_good_concept_is_not_flagged():
    concept = Concept(id=ConceptId("good"), frontmatter=Frontmatter(type="Metric"), body=GOOD_BODY)
    repo = _repo([concept])
    audit_skill = FakeQualityAuditSkill({"good": QualityAuditVerdict(standalone_quality=True)})

    assert AuditConceptQuality(repo, audit_skill).run() == []


def test_moc_and_domain_types_are_never_audited():
    moc = Concept(id=ConceptId("home"), frontmatter=Frontmatter(type="MOC"), body="")
    domain = Concept(id=ConceptId("domains/coffee"), frontmatter=Frontmatter(type="Domain"), body="")
    repo = _repo([moc, domain])
    audit_skill = FakeQualityAuditSkill(
        {
            "home": QualityAuditVerdict(standalone_quality=False, reason="would be flagged"),
            "domains/coffee": QualityAuditVerdict(standalone_quality=False, reason="would be flagged"),
        }
    )

    assert AuditConceptQuality(repo, audit_skill).run() == []

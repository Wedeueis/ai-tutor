"""Assembling the evidence `judge_relevance` decides on."""

from pipeline.application.use_cases.relevance_evidence_gatherer import (
    RelevanceEvidenceGatherer,
)
from pipeline.domain.agent import CandidateMatch, DraftConcept
from pipeline.domain.concept import Concept, ConceptId, Frontmatter, Source
from tests.application.fakes import (
    FakeConceptRepository,
    FakeMetadataRepository,
    FakeRawMaterialRepository,
)


def _draft() -> DraftConcept:
    return DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Espresso extraction"),
        body="Notes.",
        source_raw_id="r1",
    )


def _concept(concept_id: str, concept_type: str = "Playbook", sources=None) -> Concept:
    return Concept(
        id=ConceptId(concept_id),
        frontmatter=Frontmatter(type=concept_type, title=concept_id, sources=sources or []),
        body="",
    )


def _gatherer(concepts=(), category_ids=(), source_concepts=None):
    repository = FakeConceptRepository()
    metadata = FakeMetadataRepository(category_ids=list(category_ids))
    for concept in concepts:
        repository.save(concept)
        metadata.upsert(concept)  # the real index knows every concept's type
    return RelevanceEvidenceGatherer(
        metadata_repository=metadata,
        concept_repository=repository,
        raw_material_repository=FakeRawMaterialRepository(
            source_concepts=source_concepts or {}
        ),
    )


def test_the_nearest_candidate_becomes_the_similarity_signal():
    gatherer = _gatherer(concepts=[_concept("qubits")])

    evidence = gatherer.gather(
        _draft(),
        [
            CandidateMatch(concept_id=ConceptId("qubits"), score=0.91),
            CandidateMatch(concept_id=ConceptId("other"), score=0.40),
        ],
    )

    assert evidence.nearest_similarity == 0.91
    assert evidence.nearest_concept_id == "qubits"


def test_no_candidates_means_unknown_similarity_not_zero():
    """Zero would read as "unrelated to everything" and reject the draft."""
    evidence = _gatherer().gather(_draft(), [])

    assert evidence.nearest_similarity is None


def test_structural_concepts_do_not_count_toward_the_bundle_size():
    """Otherwise six real concepts plus six Categories would clear the
    topicality floor while the bundle still has nothing to be off-topic from."""
    gatherer = _gatherer(
        concepts=[
            _concept("a"),
            _concept("b"),
            _concept("brewing-methods", "Category"),
            _concept("home", "MOC"),
            _concept("references/paper", "Source Document"),
            _concept("domains/coffee", "Domain"),
        ],
        category_ids=["brewing-methods"],
    )

    assert gatherer.gather(_draft(), []).bundle_size == 2


# --- credibility signals -------------------------------------------------


def test_signals_are_read_from_the_source_hub_not_the_draft():
    """`sources[]` is stamped by IngestRawMaterial *after* the agent runs, so a
    draft never carries its own provenance when it is judged."""
    hub = _concept(
        "references/paper",
        "Source Document",
        sources=[Source(resource="raw/paper.pdf", author="Vaswani et al.")],
    )
    gatherer = _gatherer(
        concepts=[hub], source_concepts={"source-1": "references/paper"}
    )

    evidence = gatherer.gather(_draft(), [], source_id="source-1")

    assert evidence.has_credibility_signals is True


def test_a_last_modified_date_alone_counts_as_a_signal():
    hub = _concept(
        "references/paper",
        "Source Document",
        sources=[Source(resource="raw/paper.pdf", last_modified="2024-04-10")],
    )
    gatherer = _gatherer(
        concepts=[hub], source_concepts={"source-1": "references/paper"}
    )

    assert gatherer.gather(_draft(), [], source_id="source-1").has_credibility_signals


def test_a_hub_declaring_nothing_reports_no_signals():
    hub = _concept(
        "references/paper", "Source Document", sources=[Source(resource="raw/paper.pdf")]
    )
    gatherer = _gatherer(
        concepts=[hub], source_concepts={"source-1": "references/paper"}
    )

    assert gatherer.gather(_draft(), [], source_id="source-1").has_credibility_signals is False


def test_a_hand_dropped_note_has_no_source_document_and_that_is_fine():
    """No source id at all — unknown, which the curator treats as neutral."""
    evidence = _gatherer().gather(_draft(), [], source_id=None)

    assert evidence.has_credibility_signals is False


def test_a_source_id_with_no_hub_yet_does_not_raise():
    evidence = _gatherer().gather(_draft(), [], source_id="source-unknown")

    assert evidence.has_credibility_signals is False


def test_the_drafts_origin_is_not_part_of_the_evidence():
    """Tutor-written inbox material is scored like anything else (issue #7):
    where a draft came from says nothing about whether it belongs."""
    evidence = _gatherer().gather(_draft(), [])

    assert not hasattr(evidence, "origin")

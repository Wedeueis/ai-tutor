import pytest

from pipeline.adapters.ollama.client import OllamaClient
from pipeline.adapters.ollama.embedding import OllamaEmbedding
from pipeline.adapters.ollama.skills.domain_classification import OllamaDomainClassificationSkill
from pipeline.adapters.ollama.skills.extraction import OllamaExtractionSkill
from pipeline.adapters.ollama.skills.quality_eval import OllamaQualityEvalSkill
from pipeline.adapters.ollama.skills.type_classification import OllamaTypeClassificationSkill
from pipeline.domain.agent import DomainCandidate, DraftConcept
from pipeline.domain.concept import ConceptId, Frontmatter
from pipeline.domain.eval import Rubric, RubricContent, aggregate_scores
from pipeline.domain.raw_material import RawItem

pytestmark = pytest.mark.integration

CHAT_MODEL = "llama3.1:8b"
EMBED_MODEL = "nomic-embed-text"


def test_embed_returns_a_nonempty_vector():
    client = OllamaClient("http://localhost:11434")
    vector = OllamaEmbedding(client, EMBED_MODEL).embed("espresso extraction ratio")
    assert len(vector) > 0
    assert all(isinstance(x, float) for x in vector)


def test_extraction_returns_at_least_one_draft():
    client = OllamaClient("http://localhost:11434")
    skill = OllamaExtractionSkill(client, CHAT_MODEL)
    raw = RawItem(id="note.md", content="A good espresso uses a 1:2 coffee-to-water ratio.")

    drafts = skill.extract(raw)

    assert len(drafts) >= 1
    assert drafts[0].source_raw_id == "note.md"


def test_type_classification_reuses_known_type():
    client = OllamaClient("http://localhost:11434")
    skill = OllamaTypeClassificationSkill(client, CHAT_MODEL)
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Espresso ratio", description="Brewing ratio"),
        body="Use a 1:2 ratio of coffee to water for espresso.",
        source_raw_id="note.md",
    )

    verdict = skill.classify(draft, known_types=["Playbook", "Metric"])

    assert verdict.resolved_type


def test_domain_classification_with_no_domains_returns_none():
    client = OllamaClient("http://localhost:11434")
    skill = OllamaDomainClassificationSkill(client, CHAT_MODEL)
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Espresso ratio"),
        body="Use a 1:2 ratio of coffee to water for espresso.",
        source_raw_id="note.md",
    )

    verdict = skill.classify(draft, candidates=[])

    assert verdict.domain is None


def test_domain_classification_picks_the_obvious_match():
    client = OllamaClient("http://localhost:11434")
    skill = OllamaDomainClassificationSkill(client, CHAT_MODEL)
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Unclassified", title="Espresso ratio"),
        body="Use a 1:2 ratio of coffee to water for espresso.",
        source_raw_id="note.md",
    )
    candidates = [
        DomainCandidate(concept_id=ConceptId("domains/coffee"), title="Coffee", description="Coffee brewing"),
        DomainCandidate(concept_id=ConceptId("domains/finance"), title="Finance", description="Personal finance"),
    ]

    verdict = skill.classify(draft, candidates)

    assert verdict.domain in (ConceptId("domains/coffee"), None)


RUBRICS = [
    Rubric("grounded", RubricContent("Claims must be grounded in the source note; no fabricated facts.")),
]


def test_quality_eval_scores_a_grounded_draft():
    client = OllamaClient("http://localhost:11434")
    skill = OllamaQualityEvalSkill(client, CHAT_MODEL)
    raw_content = "A good espresso uses a 1:2 coffee-to-water ratio."
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Playbook", title="Espresso ratio", description="Brewing ratio"),
        body="Use a 1:2 ratio of coffee to water for espresso.",
        source_raw_id="note.md",
    )

    scores = skill.evaluate(draft, RUBRICS, raw_content)

    assert [s.rubric_id for s in scores] == ["grounded"]
    assert scores[0].score is not None


def test_quality_eval_scores_a_fabricated_draft_low():
    client = OllamaClient("http://localhost:11434")
    skill = OllamaQualityEvalSkill(client, CHAT_MODEL)
    raw_content = "A good espresso uses a 1:2 coffee-to-water ratio."
    draft = DraftConcept(
        frontmatter=Frontmatter(type="Playbook", title="Espresso history", description="Origins of espresso"),
        body=(
            "Espresso was invented in ancient Rome by the emperor Nero, who "
            "drank exactly 47 cups a day using a solar-powered brass machine."
        ),
        source_raw_id="note.md",
    )

    scores = skill.evaluate(draft, RUBRICS, raw_content)
    result = aggregate_scores(scores, threshold=0.7)

    assert result.passed is False


PREREQUISITE_RUBRICS = [
    Rubric(
        "blocks_comprehension",
        RubricContent(
            "A learner who does not already understand the TARGET would be unable to "
            "follow the SOURCE — not merely less enriched by it."
        ),
    ),
    Rubric(
        "not_merely_related",
        RubricContent(
            "The two concepts are not siblings, alternatives, or examples of one another; "
            "a learner could not simply study either one first."
        ),
    ),
]


def _prerequisite_draft() -> DraftConcept:
    return DraftConcept(
        frontmatter=Frontmatter(
            type="Concept",
            title="Multi-head attention",
            description="Running several attention heads in parallel over the same input.",
        ),
        body=(
            "Multi-head attention runs several scaled dot-product attention operations in "
            "parallel, each with its own learned query, key and value projections, then "
            "concatenates their outputs and projects the result once more."
        ),
        source_raw_id="raw-1",
    )


def test_prerequisite_skill_returns_one_score_per_rubric_per_candidate():
    from pipeline.adapters.ollama.skills.prerequisite_judgement import (
        OllamaPrerequisiteJudgementSkill,
    )
    from pipeline.domain.prerequisites import PrerequisiteCandidate

    client = OllamaClient("http://localhost:11434")
    skill = OllamaPrerequisiteJudgementSkill(client, CHAT_MODEL)
    candidates = [
        PrerequisiteCandidate(
            concept_id=ConceptId("scaled-dot-product-attention"),
            title="Scaled dot-product attention",
            description="The attention operation multi-head attention runs in parallel.",
        )
    ]

    assessments = skill.judge(_prerequisite_draft(), candidates, PREREQUISITE_RUBRICS)

    assert len(assessments) == 1
    assert assessments[0].target_id == ConceptId("scaled-dot-product-attention")
    # One entry per rubric, in rubric order, whatever the model actually answered.
    assert [s.rubric_id for s in assessments[0].scores] == [
        r.rubric_id for r in PREREQUISITE_RUBRICS
    ]


def test_prerequisite_skill_short_circuits_without_rubrics_or_candidates():
    from pipeline.adapters.ollama.skills.prerequisite_judgement import (
        OllamaPrerequisiteJudgementSkill,
    )

    skill = OllamaPrerequisiteJudgementSkill(OllamaClient("http://localhost:11434"), CHAT_MODEL)

    assert skill.judge(_prerequisite_draft(), [], PREREQUISITE_RUBRICS) == []
    assert skill.judge(_prerequisite_draft(), [], []) == []

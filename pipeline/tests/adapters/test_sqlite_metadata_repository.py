from datetime import datetime

from pipeline.adapters.sqlite.sqlite_metadata_repository import SqliteMetadataRepository
from pipeline.domain.concept import (
    Actor,
    Concept,
    ConceptId,
    Frontmatter,
    Generated,
    VerificationEvent,
)


def test_upsert_and_list_distinct_types(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body=""))
    repo.upsert(Concept(id=ConceptId("b"), frontmatter=Frontmatter(type="Metric"), body=""))
    repo.upsert(Concept(id=ConceptId("c"), frontmatter=Frontmatter(type="Playbook"), body=""))

    assert repo.list_distinct_types() == ["Metric", "Playbook"]
    repo.close()


def test_upsert_is_idempotent_by_id(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body=""))
    repo.upsert(Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Metric"), body=""))

    assert repo.list_distinct_types() == ["Metric"]
    repo.close()


def test_upsert_extracts_outbound_links(tmp_path):
    db_path = tmp_path / "metadata.db"
    repo = SqliteMetadataRepository(db_path)
    concept = Concept(
        id=ConceptId("a"),
        frontmatter=Frontmatter(type="Playbook"),
        body="See [b](/b.md) and [external](https://example.com).",
    )
    repo.upsert(concept)

    rows = repo._connection.execute("SELECT to_id FROM links WHERE from_id = 'a'").fetchall()
    assert rows == [("/b.md",)]
    repo.close()


def test_delete_removes_concept_and_links(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body="[b](b.md)"))
    repo.delete("a")

    assert repo.list_distinct_types() == []
    assert repo._connection.execute("SELECT * FROM links").fetchall() == []
    repo.close()


def test_list_distinct_types_scoped_to_domain(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(
        Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook", domain="domains/coffee"), body="")
    )
    repo.upsert(
        Concept(id=ConceptId("b"), frontmatter=Frontmatter(type="Metric", domain="domains/finance"), body="")
    )

    assert repo.list_distinct_types(domain="domains/coffee") == ["Playbook"]
    assert repo.list_distinct_types(domain="domains/finance") == ["Metric"]
    assert repo.list_distinct_types() == ["Metric", "Playbook"]
    repo.close()


def test_find_ids_by_type(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(Concept(id=ConceptId("domains/coffee"), frontmatter=Frontmatter(type="Domain"), body=""))
    repo.upsert(Concept(id=ConceptId("domains/finance"), frontmatter=Frontmatter(type="Domain"), body=""))
    repo.upsert(Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body=""))

    assert repo.find_ids_by_type("Domain") == ["domains/coffee", "domains/finance"]
    assert repo.find_ids_by_type("Metric") == []
    repo.close()


def test_trust_tier_is_persisted(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    concept = Concept(
        id=ConceptId("a"),
        frontmatter=Frontmatter(
            type="Playbook",
            generated=Generated(by=Actor("human:x"), at=datetime(2026, 1, 1)),
            verified=[VerificationEvent(by=Actor("human:x"), at=datetime(2026, 1, 1))],
        ),
        body="",
    )
    repo.upsert(concept)

    row = repo._connection.execute("SELECT trust_tier FROM concepts WHERE id = 'a'").fetchone()
    assert row[0] == "human-reviewed"
    repo.close()

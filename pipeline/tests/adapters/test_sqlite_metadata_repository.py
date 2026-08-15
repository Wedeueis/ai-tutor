from datetime import date, datetime

from pipeline.adapters.sqlite.sqlite_metadata_repository import SqliteMetadataRepository
from pipeline.domain.concept import (
    Actor,
    Concept,
    ConceptId,
    Frontmatter,
    Generated,
    TypedLink,
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


def test_find_links_returns_outgoing_and_incoming(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(
        Concept(
            id=ConceptId("quantum-computers"),
            frontmatter=Frontmatter(type="Metric"),
            body="See [Qubits](/qubits.md) for more.",
        )
    )
    repo.upsert(Concept(id=ConceptId("qubits"), frontmatter=Frontmatter(type="Metric"), body=""))

    graph = repo.find_links("quantum-computers")
    assert graph.outgoing == ["/qubits.md"]
    assert graph.incoming == []

    graph = repo.find_links("qubits")
    assert graph.outgoing == []
    assert graph.incoming == ["quantum-computers"]
    repo.close()


def test_find_links_matches_relative_and_absolute_forms(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(
        Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Metric"), body="[b](b.md)")
    )
    repo.upsert(Concept(id=ConceptId("b"), frontmatter=Frontmatter(type="Metric"), body=""))

    assert repo.find_links("b").incoming == ["a"]
    repo.close()


def test_find_links_empty_for_unlinked_concept(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Metric"), body=""))

    graph = repo.find_links("a")
    assert graph.outgoing == []
    assert graph.incoming == []
    repo.close()


def test_search_fts_ranks_by_relevance(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(
        Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body="observability logging")
    )
    repo.upsert(
        Concept(id=ConceptId("b"), frontmatter=Frontmatter(type="Playbook"), body="unrelated content")
    )

    results = repo.search_fts("logging", k=5)

    assert [r.concept_id for r in results] == [ConceptId("a")]
    repo.close()


def test_search_fts_sanitizes_special_characters(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(
        Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body='needs "quotes" AND -dashes')
    )

    results = repo.search_fts('"quotes" AND -dashes', k=5)

    assert [r.concept_id for r in results] == [ConceptId("a")]
    repo.close()


def test_search_fts_empty_query_returns_nothing(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body="hello"))

    assert repo.search_fts("", k=5) == []
    repo.close()


def test_expand_neighbors_excludes_seeds_and_respects_max_hops(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body="[b](/b.md)"))
    repo.upsert(Concept(id=ConceptId("b"), frontmatter=Frontmatter(type="Playbook"), body="[c](/c.md)"))
    repo.upsert(Concept(id=ConceptId("c"), frontmatter=Frontmatter(type="Playbook"), body=""))

    one_hop = repo.expand_neighbors(["a"], max_hops=1, decay=0.5, category_decay=0.85)
    assert one_hop == {"b": 0.5}

    two_hop = repo.expand_neighbors(["a"], max_hops=2, decay=0.5, category_decay=0.85)
    assert two_hop == {"b": 0.5, "c": 0.25}
    assert "a" not in two_hop
    repo.close()


def test_expand_neighbors_uses_category_decay_through_category_node(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Playbook"), body="[cat](/cat.md)"))
    repo.upsert(Concept(id=ConceptId("cat"), frontmatter=Frontmatter(type="Category"), body="[sibling](/sibling.md)"))
    repo.upsert(Concept(id=ConceptId("sibling"), frontmatter=Frontmatter(type="Playbook"), body=""))

    result = repo.expand_neighbors(["a"], max_hops=2, decay=0.5, category_decay=0.85)

    assert result["cat"] == 0.5  # hop from a (Playbook) -> cat, ordinary decay
    assert result["sibling"] == 0.5 * 0.85  # hop from cat (Category) -> sibling, category decay
    repo.close()


def test_find_ids_by_type_scoped_to_domain(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(
        Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Category", domain="domains/coffee"), body="")
    )
    repo.upsert(
        Concept(id=ConceptId("b"), frontmatter=Frontmatter(type="Category", domain="domains/finance"), body="")
    )

    assert repo.find_ids_by_type("Category", domain="domains/coffee") == ["a"]
    assert repo.find_ids_by_type("Category") == ["a", "b"]
    repo.close()


def test_typed_link_extracted_and_also_lands_in_plain_links(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(
        Concept(
            id=ConceptId("decisions/new"),
            frontmatter=Frontmatter(type="Decision"),
            body="supersedes:: [[/decisions/old]]",
        )
    )

    relations = repo.find_relations("decisions/new")
    assert relations == [
        TypedLink(from_id="decisions/new", to_id="/decisions/old", relation_type="supersedes")
    ]
    plain = repo._connection.execute(
        "SELECT to_id FROM links WHERE from_id = 'decisions/new'"
    ).fetchall()
    assert plain == [("/decisions/old",)]
    repo.close()


def test_find_relations_filters_by_type_and_includes_incoming(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(
        Concept(
            id=ConceptId("decisions/new"),
            frontmatter=Frontmatter(type="Decision"),
            body="supersedes:: [[/decisions/old]]\nrelates_to:: [[/decisions/other]]",
        )
    )
    repo.upsert(Concept(id=ConceptId("decisions/old"), frontmatter=Frontmatter(type="Decision"), body=""))

    outgoing_only = repo.find_relations("decisions/new", relation_type="supersedes")
    assert len(outgoing_only) == 1
    assert outgoing_only[0].relation_type == "supersedes"

    incoming = repo.find_relations("decisions/old")
    assert len(incoming) == 1
    assert incoming[0].from_id == "decisions/new"
    repo.close()


def test_trace_lineage_follows_multi_hop_chain(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(
        Concept(
            id=ConceptId("decisions/c"),
            frontmatter=Frontmatter(type="Decision"),
            body="supersedes:: [[/decisions/b]]",
        )
    )
    repo.upsert(
        Concept(
            id=ConceptId("decisions/b"),
            frontmatter=Frontmatter(type="Decision"),
            body="supersedes:: [[/decisions/a]]",
        )
    )
    repo.upsert(Concept(id=ConceptId("decisions/a"), frontmatter=Frontmatter(type="Decision"), body=""))

    paths = repo.trace_lineage("decisions/c", relation_type=None, direction="outgoing", max_hops=2)

    chains = [[link.to_id for link in path] for path in paths]
    assert ["/decisions/b"] in chains
    assert ["/decisions/b", "/decisions/a"] in chains
    repo.close()


def test_trace_lineage_returns_empty_when_no_relations(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(Concept(id=ConceptId("a"), frontmatter=Frontmatter(type="Decision"), body=""))

    assert repo.trace_lineage("a", relation_type=None, direction="both", max_hops=3) == []
    repo.close()


def test_find_by_type_and_date_filters_range(tmp_path):
    repo = SqliteMetadataRepository(tmp_path / "metadata.db")
    repo.upsert(
        Concept(
            id=ConceptId("a"),
            frontmatter=Frontmatter(
                type="Decision", generated=Generated(by=Actor("human:x"), at=datetime(2026, 5, 5))
            ),
            body="",
        )
    )
    repo.upsert(
        Concept(
            id=ConceptId("b"),
            frontmatter=Frontmatter(
                type="Decision", generated=Generated(by=Actor("human:x"), at=datetime(2026, 6, 1))
            ),
            body="",
        )
    )

    in_may = repo.find_by_type_and_date("Decision", date(2026, 5, 1), date(2026, 5, 31))
    assert in_may == ["a"]
    all_decisions = repo.find_by_type_and_date("Decision", None, None)
    assert all_decisions == ["a", "b"]
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


def test_emitted_prerequisite_edges_land_in_typed_links(tmp_path):
    """End-to-end for RF1.1's "both tiers land in `typed_links`": the domain
    emitter's exact line format has to survive the adapter's regex scrape."""
    from pipeline.domain.eval import EvalResult
    from pipeline.domain.linking import add_prerequisite_links
    from pipeline.domain.prerequisites import PrerequisiteEdge, PrerequisiteTier

    repo = SqliteMetadataRepository(tmp_path / "m.db")
    body = add_prerequisite_links(
        "Espresso extraction notes.",
        [
            PrerequisiteEdge(ConceptId("water-temperature"), PrerequisiteTier.REQUIRES, EvalResult()),
            PrerequisiteEdge(ConceptId("latte-art"), PrerequisiteTier.MAY_REQUIRE, EvalResult()),
        ],
    )
    repo.upsert(
        Concept(
            id=ConceptId("espresso-extraction"),
            frontmatter=Frontmatter(type="Playbook", title="Espresso extraction"),
            body=body,
        )
    )

    relations = repo.find_relations("espresso-extraction")
    assert {(r.relation_type, r.to_id) for r in relations} == {
        ("requires", "/water-temperature"),
        ("may_require", "/latte-art"),
    }

    # A typed link is a superset signal: it must also be in the plain graph.
    links = repo.find_links("espresso-extraction")
    assert "/water-temperature" in links.outgoing


def test_only_the_requires_tier_is_returned_when_filtering_for_it(tmp_path):
    """The planner reads `requires::` and must not see `may_require::` — the
    inert tier stays inert."""
    from pipeline.domain.eval import EvalResult
    from pipeline.domain.linking import add_prerequisite_links
    from pipeline.domain.prerequisites import PrerequisiteEdge, PrerequisiteTier

    repo = SqliteMetadataRepository(tmp_path / "m.db")
    body = add_prerequisite_links(
        "Body.",
        [
            PrerequisiteEdge(ConceptId("water-temperature"), PrerequisiteTier.REQUIRES, EvalResult()),
            PrerequisiteEdge(ConceptId("latte-art"), PrerequisiteTier.MAY_REQUIRE, EvalResult()),
        ],
    )
    repo.upsert(
        Concept(id=ConceptId("espresso"), frontmatter=Frontmatter(type="Playbook"), body=body)
    )

    relations = repo.find_relations("espresso", relation_type="requires")
    assert [r.to_id for r in relations] == ["/water-temperature"]

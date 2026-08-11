"""MetadataRepositoryPort backed by stdlib sqlite3 — structured, non-semantic
queries over concept metadata and outbound links."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from pathlib import Path

from pipeline.adapters.sqlite._thread_local_connection import ThreadLocalSqliteConnection
from pipeline.domain.agent import CandidateMatch
from pipeline.domain.concept import Concept, ConceptId, LinkGraph, TypedLink
from pipeline.domain.trust import derive_trust_tier

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
# Dataview-style inline field: `relation_type:: [[target]]` on its own line.
_TYPED_LINK_PATTERN = re.compile(r"^([a-z][a-z0-9_-]*):: \[\[([^\]]+)\]\]$", re.MULTILINE)
_FTS_TOKEN_PATTERN = re.compile(r"\w+")
_CATEGORY_TYPE = "Category"


def _extract_links(body: str) -> list[str]:
    return [
        match
        for match in _LINK_PATTERN.findall(body)
        if not match.startswith(("http://", "https://"))
    ]


def _extract_typed_links(body: str) -> list[tuple[str, str]]:
    """(relation_type, target) pairs from `relation_type:: [[target]]` lines.
    Every typed link is also woven into the plain `links` table by the
    caller — it's a superset signal, not a separate graph."""
    return _TYPED_LINK_PATTERN.findall(body)


def _fts_match_expression(query: str) -> str | None:
    """Rebuild free-text input as a safe OR-of-quoted-terms FTS5 MATCH
    expression — raw user input can contain `"`, `*`, `AND`/`OR`/`NOT`, `-`,
    which are FTS5 query-syntax operators, not literal text."""
    terms = _FTS_TOKEN_PATTERN.findall(query)
    if not terms:
        return None
    return " OR ".join(f'"{term}"' for term in terms)


def _typed_link_target_variants(concept_id: str) -> tuple[str, str, str, str]:
    """The raw forms a link to `concept_id` might use in another concept's
    `to_id` column: the two `.md`-suffixed forms a §6 markdown link
    (`[text](path.md)`) uses (mirrors `find_links`' incoming-lookup), plus
    two bare forms for typed relations' Dataview/wikilink `[[target]]`
    syntax, whose Obsidian convention is to omit `.md`. Deeper relative
    links (`../id.md`) aren't resolved here either."""
    return f"/{concept_id}.md", f"{concept_id}.md", f"/{concept_id}", concept_id


def _normalize_concept_id(raw_target: str) -> str:
    """Best-effort raw `to_id` -> canonical concept id, so multi-hop graph
    traversal can keep walking from a neighbor reached via an outgoing link.
    Inherits the same limitation as `find_links`: only the bundle-relative
    (`/id.md`) and same-directory (`id.md`) forms are resolved; a deeper
    relative link (`../id.md`) is left as-is and simply won't match further."""
    target = raw_target[1:] if raw_target.startswith("/") else raw_target
    return target[: -len(".md")] if target.endswith(".md") else target


class SqliteMetadataRepository:
    def __init__(self, db_path: Path) -> None:
        self._pool = ThreadLocalSqliteConnection(db_path, _SCHEMA_PATH)

    @property
    def _connection(self) -> sqlite3.Connection:
        return self._pool.get()

    def upsert(self, concept: Concept) -> None:
        trust_tier = derive_trust_tier(concept.frontmatter.verified)
        generated_at = (
            concept.frontmatter.generated.at.isoformat()
            if concept.frontmatter.generated and concept.frontmatter.generated.at
            else None
        )
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO concepts (id, type, title, status, trust_tier, generated_at, tags, domain)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    type=excluded.type, title=excluded.title, status=excluded.status,
                    trust_tier=excluded.trust_tier, generated_at=excluded.generated_at,
                    tags=excluded.tags, domain=excluded.domain
                """,
                (
                    str(concept.id),
                    concept.frontmatter.type,
                    concept.frontmatter.title,
                    concept.frontmatter.status,
                    trust_tier.value,
                    generated_at,
                    json.dumps(concept.frontmatter.tags),
                    concept.frontmatter.domain,
                ),
            )
            typed_links = _extract_typed_links(concept.body)

            self._connection.execute("DELETE FROM links WHERE from_id = ?", (str(concept.id),))
            self._connection.executemany(
                "INSERT OR IGNORE INTO links (from_id, to_id) VALUES (?, ?)",
                [(str(concept.id), link) for link in _extract_links(concept.body)]
                # Typed links use `[[target]]` syntax, which `_extract_links`
                # (plain `[text](path)` markdown) doesn't match — weave them
                # into `links` too, so every typed link is also an ordinary
                # untyped one (visible in Obsidian's core graph, walkable by
                # `expand_neighbors`).
                + [(str(concept.id), target) for _, target in typed_links],
            )
            self._connection.execute("DELETE FROM typed_links WHERE from_id = ?", (str(concept.id),))
            self._connection.executemany(
                "INSERT OR IGNORE INTO typed_links (from_id, to_id, relation_type) VALUES (?, ?, ?)",
                [(str(concept.id), target, relation_type) for relation_type, target in typed_links],
            )
            self._connection.execute("DELETE FROM concepts_fts WHERE id = ?", (str(concept.id),))
            self._connection.execute(
                "INSERT INTO concepts_fts (id, body) VALUES (?, ?)",
                (str(concept.id), concept.body),
            )

    def list_distinct_types(self, domain: str | None = None) -> list[str]:
        if domain is not None:
            rows = self._connection.execute(
                "SELECT DISTINCT type FROM concepts WHERE domain = ? ORDER BY type", (domain,)
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT DISTINCT type FROM concepts ORDER BY type"
            ).fetchall()
        return [row[0] for row in rows]

    def find_ids_by_type(self, concept_type: str, domain: str | None = None) -> list[str]:
        if domain is not None:
            rows = self._connection.execute(
                "SELECT id FROM concepts WHERE type = ? AND domain = ? ORDER BY id",
                (concept_type, domain),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT id FROM concepts WHERE type = ? ORDER BY id", (concept_type,)
            ).fetchall()
        return [row[0] for row in rows]

    def search_fts(self, query: str, k: int) -> list[CandidateMatch]:
        match_expression = _fts_match_expression(query)
        if match_expression is None:
            return []
        rows = self._connection.execute(
            """
            SELECT id, bm25(concepts_fts) AS rank FROM concepts_fts
            WHERE concepts_fts MATCH ? ORDER BY rank LIMIT ?
            """,
            (match_expression, k),
        ).fetchall()
        return [CandidateMatch(concept_id=ConceptId(row[0]), score=-row[1]) for row in rows]

    def expand_neighbors(
        self,
        seed_ids: list[str],
        max_hops: int,
        decay: float,
        category_decay: float,
    ) -> dict[str, float]:
        best: dict[str, float] = {}
        frontier: dict[str, float] = {seed_id: 1.0 for seed_id in seed_ids}

        for _ in range(max_hops):
            if not frontier:
                break
            frontier_ids = list(frontier.keys())
            frontier_types = self._types_of(frontier_ids)
            next_frontier: dict[str, float] = {}

            for node_id, cumulative in frontier.items():
                step_decay = category_decay if frontier_types.get(node_id) == _CATEGORY_TYPE else decay
                for neighbor_id in self._adjacent(node_id):
                    if neighbor_id in seed_ids:
                        continue
                    candidate_score = cumulative * step_decay
                    if candidate_score > best.get(neighbor_id, 0.0):
                        best[neighbor_id] = candidate_score
                        next_frontier[neighbor_id] = max(
                            next_frontier.get(neighbor_id, 0.0), candidate_score
                        )

            frontier = next_frontier

        return best

    def _types_of(self, concept_ids: list[str]) -> dict[str, str]:
        if not concept_ids:
            return {}
        placeholders = ",".join("?" * len(concept_ids))
        rows = self._connection.execute(
            f"SELECT id, type FROM concepts WHERE id IN ({placeholders})", concept_ids
        ).fetchall()
        return dict(rows)

    def _adjacent(self, concept_id: str) -> set[str]:
        """Every concept one plain-link hop from `concept_id`, in either
        direction — reuses `find_links`' best-effort id-normalization for the
        incoming direction, widened to also match wikilink-style (no `.md`)
        targets, since typed-relation lines feed `links` too."""
        variants = _typed_link_target_variants(concept_id)
        outgoing = self._connection.execute(
            "SELECT to_id FROM links WHERE from_id = ?", (concept_id,)
        ).fetchall()
        incoming = self._connection.execute(
            "SELECT from_id FROM links WHERE to_id IN (?, ?, ?, ?)", variants
        ).fetchall()
        return {_normalize_concept_id(row[0]) for row in outgoing} | {row[0] for row in incoming}

    def find_by_type_and_date(
        self, concept_type: str, since: date | None, until: date | None
    ) -> list[str]:
        query = "SELECT id FROM concepts WHERE type = ?"
        params: list = [concept_type]
        if since is not None:
            query += " AND generated_at >= ?"
            params.append(since.isoformat())
        if until is not None:
            query += " AND generated_at <= ?"
            params.append(until.isoformat())
        query += " ORDER BY id"
        rows = self._connection.execute(query, params).fetchall()
        return [row[0] for row in rows]

    def find_relations(self, concept_id: str, relation_type: str | None = None) -> list[TypedLink]:
        outgoing_query = "SELECT from_id, to_id, relation_type FROM typed_links WHERE from_id = ?"
        outgoing_params: list = [concept_id]
        variants = _typed_link_target_variants(concept_id)
        incoming_query = (
            "SELECT from_id, to_id, relation_type FROM typed_links WHERE to_id IN (?, ?, ?, ?)"
        )
        incoming_params: list = list(variants)
        if relation_type is not None:
            outgoing_query += " AND relation_type = ?"
            outgoing_params.append(relation_type)
            incoming_query += " AND relation_type = ?"
            incoming_params.append(relation_type)

        outgoing = self._connection.execute(outgoing_query, outgoing_params).fetchall()
        incoming = self._connection.execute(incoming_query, incoming_params).fetchall()
        return [
            TypedLink(from_id=row[0], to_id=row[1], relation_type=row[2])
            for row in (*outgoing, *incoming)
        ]

    def trace_lineage(
        self,
        concept_id: str,
        relation_type: str | None,
        direction: str,
        max_hops: int,
    ) -> list[list[TypedLink]]:
        paths: list[list[TypedLink]] = []
        self._walk_lineage(concept_id, relation_type, direction, max_hops, [], {concept_id}, paths)
        return paths

    def _walk_lineage(
        self,
        node_id: str,
        relation_type: str | None,
        direction: str,
        max_hops: int,
        path: list[TypedLink],
        visited: set[str],
        paths: list[list[TypedLink]],
    ) -> None:
        if len(path) >= max_hops:
            return

        steps: list[tuple[str, str, str]] = []  # (from_id, to_id, relation_type)
        if direction in ("outgoing", "both"):
            for row in self._typed_outgoing(node_id, relation_type):
                steps.append(row)
        if direction in ("incoming", "both"):
            for row in self._typed_incoming(node_id, relation_type):
                steps.append(row)

        for from_id, to_id, rtype in steps:
            next_id = _normalize_concept_id(to_id) if from_id == node_id else from_id
            if next_id in visited:
                continue
            new_path = [*path, TypedLink(from_id=from_id, to_id=to_id, relation_type=rtype)]
            paths.append(new_path)
            self._walk_lineage(
                next_id, relation_type, direction, max_hops, new_path, visited | {next_id}, paths
            )

    def _typed_outgoing(self, node_id: str, relation_type: str | None) -> list[tuple[str, str, str]]:
        query = "SELECT from_id, to_id, relation_type FROM typed_links WHERE from_id = ?"
        params: list = [node_id]
        if relation_type is not None:
            query += " AND relation_type = ?"
            params.append(relation_type)
        return self._connection.execute(query, params).fetchall()

    def _typed_incoming(self, node_id: str, relation_type: str | None) -> list[tuple[str, str, str]]:
        variants = _typed_link_target_variants(node_id)
        query = "SELECT from_id, to_id, relation_type FROM typed_links WHERE to_id IN (?, ?, ?, ?)"
        params: list = list(variants)
        if relation_type is not None:
            query += " AND relation_type = ?"
            params.append(relation_type)
        return self._connection.execute(query, params).fetchall()

    def find_links(self, concept_id: str) -> LinkGraph:
        outgoing = [
            row[0]
            for row in self._connection.execute(
                "SELECT to_id FROM links WHERE from_id = ? ORDER BY to_id", (concept_id,)
            ).fetchall()
        ]
        # `to_id` is whatever raw string the source markdown link used (see
        # _extract_links) — match both the recommended bundle-relative form
        # (`/id.md`) and a same-directory relative form (`id.md`) when
        # looking up who links back to this concept. Links using a deeper
        # relative path (`../id.md`) aren't resolved here.
        incoming = [
            row[0]
            for row in self._connection.execute(
                "SELECT from_id FROM links WHERE to_id IN (?, ?) ORDER BY from_id",
                (f"/{concept_id}.md", f"{concept_id}.md"),
            ).fetchall()
        ]
        return LinkGraph(concept_id=concept_id, outgoing=outgoing, incoming=incoming)

    def delete(self, concept_id: str) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM concepts WHERE id = ?", (concept_id,))
            self._connection.execute("DELETE FROM links WHERE from_id = ?", (concept_id,))
            self._connection.execute("DELETE FROM typed_links WHERE from_id = ?", (concept_id,))
            self._connection.execute("DELETE FROM concepts_fts WHERE id = ?", (concept_id,))

    def close(self) -> None:
        self._pool.close()

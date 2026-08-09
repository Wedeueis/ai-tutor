"""MetadataRepositoryPort backed by stdlib sqlite3 — structured, non-semantic
queries over concept metadata and outbound links."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from pipeline.domain.concept import Concept
from pipeline.domain.trust import derive_trust_tier

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _extract_links(body: str) -> list[str]:
    return [
        match
        for match in _LINK_PATTERN.findall(body)
        if not match.startswith(("http://", "https://"))
    ]


class SqliteMetadataRepository:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(db_path)
        self._connection.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        self._connection.commit()

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
            self._connection.execute("DELETE FROM links WHERE from_id = ?", (str(concept.id),))
            self._connection.executemany(
                "INSERT OR IGNORE INTO links (from_id, to_id) VALUES (?, ?)",
                [(str(concept.id), link) for link in _extract_links(concept.body)],
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

    def find_ids_by_type(self, concept_type: str) -> list[str]:
        rows = self._connection.execute(
            "SELECT id FROM concepts WHERE type = ? ORDER BY id", (concept_type,)
        ).fetchall()
        return [row[0] for row in rows]

    def delete(self, concept_id: str) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM concepts WHERE id = ?", (concept_id,))
            self._connection.execute("DELETE FROM links WHERE from_id = ?", (concept_id,))

    def close(self) -> None:
        self._connection.close()

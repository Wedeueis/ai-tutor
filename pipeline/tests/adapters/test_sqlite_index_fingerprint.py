"""`SqliteIndexFingerprint` — one row, by construction."""

from __future__ import annotations

import sqlite3

import pytest

from pipeline.adapters.sqlite.sqlite_index_fingerprint import SqliteIndexFingerprint
from pipeline.application.ports.index_fingerprint import IndexFingerprint

QWEN = IndexFingerprint(
    embed_model="qwen3-embedding:0.6b",
    dimensions=1024,
    query_instruction="Given a search query, retrieve relevant passages",
)


@pytest.fixture
def fingerprints(tmp_path):
    return SqliteIndexFingerprint(tmp_path / "metadata.db")


def test_an_empty_index_reads_as_none(fingerprints):
    assert fingerprints.read() is None


def test_a_fingerprint_round_trips(fingerprints):
    fingerprints.write(QWEN)

    assert fingerprints.read() == QWEN


def test_writing_twice_replaces_rather_than_appends(fingerprints, tmp_path):
    """Two rows would mean two answers to a question with one answer — the
    `CHECK (id = 1)` makes that unrepresentable rather than merely unlikely."""
    fingerprints.write(QWEN)
    replacement = IndexFingerprint(embed_model="nomic-embed-text", dimensions=768)

    fingerprints.write(replacement)

    assert fingerprints.read() == replacement
    connection = sqlite3.connect(tmp_path / "metadata.db")
    assert connection.execute("SELECT count(*) FROM index_fingerprint").fetchone()[0] == 1


def test_clearing_leaves_nothing(fingerprints):
    fingerprints.write(QWEN)

    fingerprints.clear()

    assert fingerprints.read() is None


def test_an_empty_query_instruction_survives(fingerprints):
    """The empty string means "no prefix", which is a real configuration for a
    non-instruct model — not a missing value."""
    bare = IndexFingerprint(embed_model="nomic-embed-text", dimensions=768)

    fingerprints.write(bare)

    assert fingerprints.read().query_instruction == ""

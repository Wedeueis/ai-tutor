"""Refusing an index a different embedding model built.

This guard exists because the failure it catches is invisible. Two embedding
models' vectors in one Chroma collection do not error: cosine distance
compares the unrelated spaces happily and returns confident nonsense, every
search degrades, and nothing in any store says why. Before this, the only
defence was a comment asking people not to change `OLLAMA_EMBED_MODEL`.

So the tests that matter here are the ones asserting it *raises*, and that the
message tells the operator what to run.
"""

from __future__ import annotations

import pytest

from pipeline.application.ports.index_fingerprint import IndexFingerprint
from pipeline.application.use_cases.ensure_index_fingerprint import (
    EnsureIndexFingerprint,
    IndexFingerprintMismatch,
)

QWEN = "qwen3-embedding:0.6b"
NOMIC = "nomic-embed-text"
INSTRUCTION = "Given a search query, retrieve relevant passages"


class FakeFingerprints:
    def __init__(self, stored: IndexFingerprint | None = None) -> None:
        self.stored = stored

    def read(self) -> IndexFingerprint | None:
        return self.stored

    def write(self, fingerprint: IndexFingerprint) -> None:
        self.stored = fingerprint

    def clear(self) -> None:
        self.stored = None


def guard(stored=None, model=QWEN, instruction="") -> EnsureIndexFingerprint:
    return EnsureIndexFingerprint(FakeFingerprints(stored), model, instruction)


# --- the check ------------------------------------------------------------


def test_an_unrecorded_index_is_not_a_mismatch():
    """Nothing indexed yet is a new index, not a corrupt one — the distinction
    the whole guard turns on."""
    guard().check()


def test_a_changed_embedding_model_is_refused():
    stored = IndexFingerprint(embed_model=NOMIC, dimensions=768)

    with pytest.raises(IndexFingerprintMismatch):
        guard(stored, model=QWEN).check()


def test_the_refusal_names_both_models_and_the_remedy():
    """A guard that raises something the operator cannot act on is barely
    better than no guard."""
    stored = IndexFingerprint(embed_model=NOMIC, dimensions=768)

    with pytest.raises(IndexFingerprintMismatch) as raised:
        guard(stored, model=QWEN).check()

    message = str(raised.value)
    assert NOMIC in message
    assert QWEN in message
    assert "768" in message
    assert "pipeline clear --all" in message


def test_the_same_model_passes():
    stored = IndexFingerprint(embed_model=QWEN, dimensions=1024)

    guard(stored, model=QWEN).check()


def test_the_check_is_memoized():
    """It fronts `IndexConcept.run`, which runs once per concept; re-reading
    an answer that cannot change mid-process would be a query per concept."""
    fingerprints = FakeFingerprints(IndexFingerprint(embed_model=QWEN, dimensions=1024))
    ensure = EnsureIndexFingerprint(fingerprints, QWEN)
    ensure.check()

    # A model swap mid-process cannot happen, so a stale pass is correct here.
    fingerprints.stored = IndexFingerprint(embed_model=NOMIC, dimensions=768)
    ensure.check()


# --- the query instruction is not fatal -----------------------------------


def test_a_changed_query_instruction_is_recorded_not_refused():
    """Stored vectors carry no instruction, so they stay valid — only what a
    query retrieves shifts. Refusing here would make retuning retrieval
    require a full reindex for no reason."""
    fingerprints = FakeFingerprints(
        IndexFingerprint(embed_model=QWEN, dimensions=1024, query_instruction="old")
    )

    EnsureIndexFingerprint(fingerprints, QWEN, INSTRUCTION).check()

    assert fingerprints.stored.query_instruction == INSTRUCTION
    assert fingerprints.stored.embed_model == QWEN
    assert fingerprints.stored.dimensions == 1024


# --- recording ------------------------------------------------------------


def test_the_first_vector_stamps_the_index():
    fingerprints = FakeFingerprints()
    ensure = EnsureIndexFingerprint(fingerprints, QWEN, INSTRUCTION)

    ensure.record([0.0] * 1024)

    assert fingerprints.stored == IndexFingerprint(
        embed_model=QWEN, dimensions=1024, query_instruction=INSTRUCTION
    )


def test_the_dimension_comes_from_the_model_not_from_config():
    """It is the one value that proves the vectors really came from the model
    the name claims."""
    fingerprints = FakeFingerprints()

    EnsureIndexFingerprint(fingerprints, QWEN).record([0.0] * 768)

    assert fingerprints.stored.dimensions == 768


def test_recording_does_not_overwrite_an_existing_fingerprint():
    stored = IndexFingerprint(embed_model=QWEN, dimensions=1024)
    fingerprints = FakeFingerprints(stored)

    EnsureIndexFingerprint(fingerprints, QWEN).record([0.0] * 4)

    assert fingerprints.stored == stored


# --- forgetting -----------------------------------------------------------


def test_forgetting_clears_the_record_and_the_memo():
    """The vectors went away; a fingerprint describing an index that no longer
    exists would make a deliberate model change look like corruption."""
    fingerprints = FakeFingerprints(
        IndexFingerprint(embed_model=NOMIC, dimensions=768)
    )
    ensure = EnsureIndexFingerprint(fingerprints, NOMIC)
    ensure.check()

    ensure.forget()

    assert fingerprints.stored is None
    # And a different model is now accepted, because there is nothing to clash.
    EnsureIndexFingerprint(fingerprints, QWEN).check()

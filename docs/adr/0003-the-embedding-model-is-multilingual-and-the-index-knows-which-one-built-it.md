# The embedding model is multilingual, and the index knows which one built it

The default embedding model is **`qwen3-embedding:0.6b`**, replacing
`nomic-embed-text`. Queries are prefixed with an instruction and documents are
not. A new `index_fingerprint` table records which model built the index, and a
mismatch raises rather than degrading search.

## Why the model changed

The vault takes material in English **and** Portuguese. `nomic-embed-text` is
English-centric, and the consequence is not a mild quality dip — it is a broken
retrieval path. Measured locally, cosine similarity of an English query against
three documents:

| model | EN query → PT answer | EN query → EN answer | EN query → unrelated |
|---|---|---|---|
| `qwen3-embedding:0.6b` | **0.737** | 0.749 | 0.169 |
| `nomic-embed-text` | **0.401** | 0.715 | 0.328 |

Read the last two columns of the nomic row together. The correct answer in
Portuguese scores 0.401; a completely unrelated Portuguese sentence about cold
brew scores 0.328. **The margin is 0.073.** An English query could not reliably
tell a correct Portuguese concept from an irrelevant one, and the hybrid
search's other legs (lexical BM25, graph expansion) do not rescue this —
lexical matching across languages fails for the same reason the vector does.

Qwen3's cross-lingual gap is 0.012 against a separation of 0.57 from noise.

`0.6b` rather than the stronger `4b` for a hardware reason, not a quality one:
ingest alternates chat and embedding calls per chunk, and both models share one
8GB GPU with `qwen3.5:4b` (3.4GB). At ~640MB the small one stays resident; the
4B would force an evict/reload on every alternation.

## Why queries and documents are separate verbs

`EmbeddingPort.embed(text)` became `embed_document(text)` and
`embed_query(text, task=None)`.

Instruction-aware embedding models expect an asymmetry — Qwen3 wants
`Instruct: <task>\nQuery: <text>` on the query side and bare text on the
document side; `nomic-embed-text` wanted `search_query:` / `search_document:`.
Sending one where the other belongs costs real retrieval quality.

**This repo was silently paying that cost.** A grep for
`search_document|search_query|prefix` across `pipeline/src` returned nothing:
`nomic-embed-text` had been used unprefixed on both sides since the first
commit, which is a documented 5–10 point retrieval loss. One `embed()` with a
defaulted meaning is what allowed it — every call site meant "document",
including the one embedding the user's search query, and nothing in the type
system could point at the mistake.

Two verbs make each call site state which side it is on. Of the five, exactly
one is a query (`SearchConcepts.run`); the other four are document-vs-document
similarity, where a query prefix would skew the comparison. `FakeEmbedding`
returns *different* vectors per side so a swapped call fails a test.

A useful property falls out: because the document side carries no instruction,
`EMBED_QUERY_INSTRUCTION` can be retuned at any time **without re-indexing a
single vector**.

## Why the index records its own fingerprint

Mixing two embedding models' vectors in one Chroma collection does not error.
Cosine distance compares the unrelated spaces happily and returns confident
nonsense. Every search degrades, and nothing in any store says why.

Before this, the only defence was a comment — repeated in `cli/main.py`,
`config.py` and `ports/chat_model.py` — asking people not to change
`OLLAMA_EMBED_MODEL`. That comment was load-bearing for correctness, which is
not a job a comment can do. This ADR exists partly because *the change it
documents would have been dangerous under the old regime*: swapping the model
is exactly the operation that was unguarded.

`index_fingerprint` holds one row: model, dimension, query instruction. The
dimension is taken from the model's first actual output rather than from
config, because that is the value that proves the vectors came from the model
the name claims. A mismatched model raises `IndexFingerprintMismatch` naming
both models and the remedy. A changed *instruction* only warns and re-records —
stored vectors are unaffected, so refusing would force a pointless reindex.

`ClearBundle` forgets the fingerprint when it removes the vectors, so a
deliberate model change after a reset does not look like corruption.

## What this does not cover

Embeddings remain **local unconditionally**, off the `CHAT_PROVIDER` seam
(PRD v3 NFR1, issue #19). The fingerprint makes that boundary checkable; it
does not move it.

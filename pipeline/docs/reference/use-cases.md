# Use Cases

Everything under `src/pipeline/application/use_cases/`. Each entry lists the
constructor's port dependencies, the `run(...)` signature, and what it
actually does. See [Architecture → Data flow](../architecture/data-flow.md)
for how these compose end-to-end.

## `ScanIntake`

*File: `scan_intake.py`*

**Depends on:** `FileSystemScannerPort`, `IntakeRepositoryPort`

**`run(root: str) -> list[IntakeItem]`** — enumerates files under `root` via
the scanner, classifies each by extension (`classify_kind`), skips anything
unrecognized or already tracked at the same content hash, and registers the
rest as new `IntakeItem`s in state `discovered`. Returns only the newly
discovered items. If a path's content changed and the old item at that path
never got past `discovered`/`error` (nothing was derived from it), the old
row is deleted rather than left as an orphan; `parsed`/`ingested`/`rejected`
items are always kept as history.

## `PruneStaleIntake`

*File: `prune_stale_intake.py`*

**Depends on:** `IntakeRepositoryPort`

**`run() -> list[IntakeItem]`** — deletes and returns every intake item
`IntakeRepositoryPort.list_stale_duplicates()` reports: rows superseded by a
later hash at the same path that never got past `discovered`/`error`, i.e.
nothing was ever derived from them. Items that reached `parsed`/`ingested`/
`rejected` are never candidates, even once superseded — they're the audit
record of what actually happened, not orphaned noise. Backs `pipeline
prune`.

## `ParseSourceDocuments`

*File: `parse_source_documents.py`*

**Depends on:** `IntakeRepositoryPort`, `DocumentParsingPort`,
`ImageCaptioningSkillPort`, `ConceptRepositoryPort`, `IndexConcept`,
`BundleLogPort`

**`run() -> list[ParseOutcome]`** — for every `discovered` `SOURCE_DOCUMENT`:
first `_ensure_source_hub` creates a durable `references/<slug>.md` stub
concept for the document (`type: Source Document`) the first time it's
parsed — idempotent across re-parses, checked via
`IntakeRepositoryPort.list_concepts_for(source.id)` and linked back the same
way (`link_concept`). Then parses it, captions and inlines any extracted
images, splits the result with `chunk_markdown()`, and writes each chunk as
a new `CHUNK`-kind `IntakeItem` in state `discovered` — except any chunk
`domain/text_quality.py::looks_like_garbled_table` flags as a mangled table
dump rather than prose, which is skipped instead (counted in
`ParseOutcome.skipped`, never reaches extraction). Marks the source document
`parsed`. `ParseOutcome` carries `source_id`, the resulting `chunk_ids`, and
`skipped`.

## `KnowledgeAgent`

*File: `knowledge_agent.py`*

**Depends on:** `ExtractionSkillPort`, `EmbeddingPort`, `VectorSearchPort`,
`EntityDisambiguationSkillPort`, `TypeClassificationSkillPort`,
`DomainClassificationSkillPort`, `QualityEvalSkillPort`,
`RelatednessSkillPort`, `EvalRubricsRepositoryPort`, `MetadataRepositoryPort`,
`ConceptRepositoryPort`

**`run(raw: RawItem) -> AgentResult`** — orchestrates every LLM-backed skill
over one raw item: extract candidate drafts, classify each draft's domain,
search for existing candidates scoped to that domain, disambiguate
(merge vs. new), classify type for genuinely-new drafts, run quality eval,
judge which non-merged candidates are genuinely related and weave §6 links
to them into the draft's body, and resolve each draft to a `CreateDecision`,
`MergeDecision`, or `RejectDecision`. **Does not write anything itself** —
it's pure decision logic; `IngestRawMaterial` applies the decisions. Full
flow diagram:
[Architecture → Data flow § `KnowledgeAgent.run(raw)`](../architecture/data-flow.md#4-knowledgeagentrunraw-the-judgment-pipeline).

Constructor also takes two tunable thresholds:
`disambiguation_confidence_threshold` (default `0.75`) and `eval_threshold`
(default `0.7`, from `domain/eval.py::DEFAULT_EVAL_THRESHOLD`).

## `IngestRawMaterial`

*File: `ingest_raw_material.py`*

**Depends on:** `RawMaterialRepositoryPort`, `KnowledgeAgent`,
`ConceptRepositoryPort`, `IndexConcept`, `BundleLogPort`

**`run() -> list[IngestOutcome]`** — pulls every unprocessed raw item, runs
it through `KnowledgeAgent`, and applies the resulting decisions: writes new
concepts (slugifying titles into unique `ConceptId`s via `domain/slug.py::
slugify`), appends merge additions to existing concepts' bodies, re-indexes
anything that changed, logs every outcome to the SQLite audit trail
(`BundleLogPort`), and marks each raw item processed or rejected.
`IngestOutcome` carries `raw_id`, `created`, `merged_into`, `rejected`
(rationale strings).

If the raw item is a chunk from a parsed source document
(`RawItem.source_id` set) and that source already has a `references/` hub
(`RawMaterialRepositoryPort.find_source_concept`), every concept created or
merged from it gets a §5.1 `sources[]` entry pointing at the hub (deduped by
resource), and the hub's own `## Derived concepts` list gets a reciprocal
link back (`domain/linking.py::add_link_section`, deduped/idempotent) — the
same shape as the relatedness backlinks below, just for source-document
provenance instead of semantic relatedness.

## `IndexConcept`

*File: `index_concept.py`*

**Depends on:** `EmbeddingPort`, `VectorSearchPort`, `MetadataRepositoryPort`

**`run(concept: Concept) -> None`** — for content types (anything except
`MOC`/`Domain`, see `domain/concept.py::NON_CONTENT_TYPES`): embeds the body
and upserts into the vector store with `{"type", "domain"}` metadata. For
**every** concept regardless of type: upserts into the metadata repository
(domain classification needs to enumerate `Domain` concepts via
`find_ids_by_type`, so they can't be excluded from the metadata store the way
they are from the vector store).

## `AuditConceptQuality`

*File: `audit_concept_quality.py`*

**Depends on:** `ConceptRepositoryPort`, `QualityAuditSkillPort`

**`run() -> list[QualityFlag]`** — walks every content concept (`MOC`/
`Domain` skipped, see `NON_CONTENT_TYPES`), and flags anything that doesn't
stand alone as genuinely useful. A free, no-LLM check
(`domain/text_quality.py::looks_like_garbled_table`) short-circuits the
obvious case (a mangled table dump) without an LLM call; everything else
goes through `QualityAuditSkillPort.judge`, which can catch a
grammatically-fine-but-vacuous fragment the lexical check can't
distinguish from real prose. `QualityFlag` carries `concept_id` and
`reason`. Purely a report — pairs with `pipeline delete` (no use case of
its own; `Container` calls `ConceptRepositoryPort.delete` +
`MetadataRepositoryPort.delete` + `VectorSearchPort.delete` directly) for
the actual cleanup action. Backs `pipeline audit`.

## `RebuildIndex`

*File: `rebuild_index.py`*

**Depends on:** `ConceptRepositoryPort`, `IndexConcept`

**`run() -> int`** — walks every concept id in the vault, loads and
re-indexes each one via `IndexConcept`, returns the count. Use to recover
from a stale or corrupted vector/metadata store, since both are fully
derivable from the vault's markdown files.

## `SearchConcepts`

*File: `search_concepts.py`*

**Depends on:** `EmbeddingPort`, `VectorSearchPort`

**`run(query: str, k: int = 5) -> list[CandidateMatch]`** — embeds the query
and returns the `k` closest concepts by vector similarity. The thinnest use
case in the codebase — no logic beyond the two port calls. Backs both
`pipeline search` and the `search_wiki` MCP tool.

## `ValidateConcept`

*File: `validate_concept.py`*

**Depends on:** `SchemaRegistryPort`, optionally a `ConformanceChecker`
(defaults to `domain.conformance.ConformanceChecker()`)

**`run(concept: Concept) -> ValidationResult`** — runs the OKF §11 structural
conformance check, then looks up and validates against the concept's `type`
JSON Schema (falling back to `_base.schema.json`) with
`jsonschema.Draft202012Validator`. Combines both sets of issues into one
result. This is *structural* validation — distinct from the quality-eval
skill, which judges content quality, not document shape.

## `AttestComputation`

*File: `attest_computation.py`*

**Depends on:** `ExecutorPort`, `AttesterPort`

**`run(computation: str, parameters: dict, contract: dict) -> Verdict`** —
runs the named computation via the executor, then verifies the resulting
`Receipt` against `contract` via the attester. Fully wired and tested against
fakes, but both ports currently only have `NotImplementedError` stub
adapters — see
[Architecture → Ports & adapters § Stub adapters](../architecture/ports-and-adapters.md#stub-adapters-not-yet-implemented).
This is the OKF §10 Attested Computation seam, waiting on a real
`Executor`/`Attester` pair and a concept in the vault that declares
`type: Attested Computation`.

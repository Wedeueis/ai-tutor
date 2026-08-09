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
discovered items.

## `ParseSourceDocuments`

*File: `parse_source_documents.py`*

**Depends on:** `IntakeRepositoryPort`, `DocumentParsingPort`,
`ImageCaptioningSkillPort`

**`run() -> list[ParseOutcome]`** — for every `discovered` `SOURCE_DOCUMENT`:
parses it, captions and inlines any extracted images, splits the result with
`chunk_markdown()`, and writes each chunk as a new `CHUNK`-kind `IntakeItem`
in state `discovered`. Marks the source document `parsed`. `ParseOutcome`
carries `source_id` and the resulting `chunk_ids`.

## `KnowledgeAgent`

*File: `knowledge_agent.py`*

**Depends on:** `ExtractionSkillPort`, `EmbeddingPort`, `VectorSearchPort`,
`EntityDisambiguationSkillPort`, `TypeClassificationSkillPort`,
`DomainClassificationSkillPort`, `QualityEvalSkillPort`,
`EvalRubricsRepositoryPort`, `MetadataRepositoryPort`,
`ConceptRepositoryPort`

**`run(raw: RawItem) -> AgentResult`** — orchestrates every LLM-backed skill
over one raw item: extract candidate drafts, classify each draft's domain,
search for existing candidates scoped to that domain, disambiguate
(merge vs. new), classify type for genuinely-new drafts, run quality eval,
and resolve each draft to a `CreateDecision`, `MergeDecision`, or
`RejectDecision`. **Does not write anything itself** — it's pure decision
logic; `IngestRawMaterial` applies the decisions. Full flow diagram:
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
concepts (slugifying titles into unique `ConceptId`s via `_slugify`), appends
merge additions to existing concepts' bodies, re-indexes anything that
changed, logs every outcome to `log.md`, and marks each raw item processed or
rejected. `IngestOutcome` carries `raw_id`, `created`, `merged_into`,
`rejected` (rationale strings).

## `IndexConcept`

*File: `index_concept.py`*

**Depends on:** `EmbeddingPort`, `VectorSearchPort`, `MetadataRepositoryPort`

**`run(concept: Concept) -> None`** — for content types (anything except
`MOC`/`Domain`, see `_NON_CONTENT_TYPES`): embeds the body and upserts into
the vector store with `{"type", "domain"}` metadata. For **every** concept
regardless of type: upserts into the metadata repository (domain
classification needs to enumerate `Domain` concepts via
`find_ids_by_type`, so they can't be excluded from the metadata store the way
they are from the vector store).

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

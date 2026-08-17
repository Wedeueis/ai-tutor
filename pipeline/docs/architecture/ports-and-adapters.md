# Ports & Adapters

Every row is a `typing.Protocol` in `application/ports/` and the concrete
class(es) in `adapters/` that implement it, wired together in
`cli/main.py`'s `Container`. Adapters satisfy ports structurally — none of
them inherit from the `Protocol` class.

## Core ports

| Port (`application/ports/`) | Method surface | Adapter (`adapters/`) | Backing technology |
|---|---|---|---|
| `ConceptRepositoryPort` | `load`, `save`, `list`, `exists`, `delete` | `filesystem.markdown_concept_repository.MarkdownConceptRepository` | Markdown + YAML frontmatter files under the vault root, via `frontmatter_codec.py` / `frontmatter_mapping.py` |
| `VectorSearchPort` | `upsert`, `query`, `delete` | `chroma.chroma_vector_search.ChromaVectorSearch` | A persistent ChromaDB collection (`concepts`, cosine space) |
| `MetadataRepositoryPort` | `upsert`, `list_distinct_types`, `find_ids_by_type`, `find_links`, `delete` | `sqlite.sqlite_metadata_repository.SqliteMetadataRepository` | SQLite `concepts` + `links` tables |
| `EmbeddingPort` | `embed_document`, `embed_query` | `ollama.embedding.OllamaEmbedding` | Ollama `/api/embeddings`, via `ollama.client.OllamaClient`. Two verbs because the query/document asymmetry belongs to the model: `qwen3-embedding` wants `Instruct: <task>\nQuery: <text>` on queries and bare text on documents. Exactly one call site is a query (`SearchConcepts.run`); the other four are document-vs-document similarity. See [ADR 0003](../../../docs/adr/0003-the-embedding-model-is-multilingual-and-the-index-knows-which-one-built-it.md). |
| `PassageReaderPort` | `for_concept`, `neighbours` | `sqlite.sqlite_passage_reader.SqlitePassageReader` | SQLite `intake_items` joined through `intake_item_concepts`. Read-only by design: passages are written by `parse-sources` as a side effect of chunking, and a port that could also create one would invite a second writer for material that must stay a faithful copy of the source. The intake store is a work queue, so `pipeline clear --reset-intake` empties it and recall degrades to "nothing recorded" — making passages durable means moving them to their own table and swapping this adapter, with no caller changing. |
| `IndexFingerprintPort` | `read`, `write`, `clear` | `sqlite.sqlite_index_fingerprint.SqliteIndexFingerprint` | SQLite `index_fingerprint` table — one row recording which embedding model and dimension produced the vectors currently in ChromaDB. Two models' vectors in one collection do not error, they return confident nonsense; `EnsureIndexFingerprint` turns that into `IndexFingerprintMismatch` at the first index write or search. |
| `FileSystemScannerPort` | `scan`, `read_text` | `filesystem.filesystem_scanner.FilesystemScanner` | Local filesystem, SHA-256 content hashing |
| `IntakeRepositoryPort` | `find_by_path`, `upsert`, `get`, `list_by_state`, `list_children`, `link_concept`, `list_concepts_for` | `sqlite.sqlite_intake_repository.SqliteIntakeRepository` | SQLite `intake_items` + `intake_item_concepts` tables |
| `RawMaterialRepositoryPort` | `list_unprocessed`, `mark_processed`, `mark_rejected`, `link_concept`, `find_source_concept` | `filesystem.raw_material_repository.FilesystemRawMaterialRepository` | Reads through `IntakeRepositoryPort` + `FileSystemScannerPort` — state lives in the intake DB, not on disk. `find_source_concept` resolves a chunk's source-document id to its `references/` hub concept id, via `IntakeRepositoryPort.list_concepts_for` (the same link table chunk↔concept links use). |
| `DocumentParsingPort` | `parse` | `docling.document_parser.DoclingDocumentParser` | [Docling](https://github.com/docling-project/docling) — layout-aware PDF/DOCX/PPTX/XLSX/image parsing |
| `SchemaRegistryPort` | `get_schema` | `schema_registry.json_file_schema_registry.JsonFileSchemaRegistry` | `pipeline/schemas/<Type>.schema.json`, falling back to `_base.schema.json` |
| `EvalRubricsRepositoryPort` | `load_for_domain` | `eval_rubrics.json_file_eval_rubrics_repository.JsonFileEvalRubricsRepository` | `pipeline/evals/<domain-id>.json`, falling back to `_base.json` |
| `BundleLogPort` | `append`, `list_entries`, `clear` | `sqlite.sqlite_bundle_log.SqliteBundleLog` | SQLite `bundle_log` table — structured ingest audit trail. This is pipeline governance state, not vault content: WIKI_SPEC.md §9's `log.md` is optional and this bundle intentionally doesn't populate it (see `pipeline log`, the `okf://log` MCP resource). |
| `ExecutorPort` | `run` | `stubs.not_implemented_executor.NotImplementedExecutor` | **Stub** — raises `NotImplementedError` (OKF §10.2, no computation exists yet) |
| `AttesterPort` | `verify` | `stubs.not_implemented_attester.NotImplementedAttester` | **Stub** — raises `NotImplementedError` (OKF §10.2) |

## Skill ports (`application/ports/skills/`)

All seven are LLM-backed judgment calls, and all seven currently have exactly
one adapter, backed by a local Ollama chat or vision model via the shared
`adapters/ollama/client.py::OllamaClient`.

| Port | Method | Adapter | Model used |
|---|---|---|---|
| `ExtractionSkillPort` | `extract(raw) -> list[DraftConcept]` | `ollama.skills.extraction.OllamaExtractionSkill` | `OLLAMA_CHAT_MODEL` |
| `EntityDisambiguationSkillPort` | `disambiguate(draft, candidates) -> DisambiguationVerdict` | `ollama.skills.entity_disambiguation.OllamaEntityDisambiguationSkill` | `OLLAMA_CHAT_MODEL` |
| `TypeClassificationSkillPort` | `classify(draft, known_types) -> TypeClassificationVerdict` | `ollama.skills.type_classification.OllamaTypeClassificationSkill` | `OLLAMA_CHAT_MODEL` |
| `DomainClassificationSkillPort` | `classify(draft, candidates) -> DomainClassificationVerdict` | `ollama.skills.domain_classification.OllamaDomainClassificationSkill` | `OLLAMA_CHAT_MODEL` |
| `QualityEvalSkillPort` | `evaluate(draft, rubrics, raw_content) -> list[RubricScore]` | `ollama.skills.quality_eval.OllamaQualityEvalSkill` | `OLLAMA_CHAT_MODEL` |
| `QualityAuditSkillPort` | `judge(concept) -> QualityAuditVerdict` | `ollama.skills.quality_audit.OllamaQualityAuditSkill` | `OLLAMA_CHAT_MODEL` |
| `RelatednessSkillPort` | `judge(draft, candidates) -> RelatednessVerdict` | `ollama.skills.relatedness.OllamaRelatednessSkill` | `OLLAMA_RELATEDNESS_MODEL` |
| `ImageCaptioningSkillPort` | `caption(image) -> str` | `ollama.skills.image_captioning.OllamaImageCaptioningSkill` | `OLLAMA_VISION_MODEL` |

`QualityAuditSkillPort` is the odd one out structurally: every other skill
judges a fresh `DraftConcept` during ingest; this one judges an
already-published `Concept` on demand (`pipeline audit`), asking whether its
body stands alone as genuinely useful rather than being a thin/vacuous
fragment — the retroactive counterpart to `QualityEvalSkillPort`, which only
ever sees content at creation/merge time against its raw source.

Every skill adapter follows the same shape: a module-level `_PROMPT`
template instructing the model to respond with **only** a JSON value, a
class taking `(OllamaClient, model)`, and one method that formats the
prompt, calls `OllamaClient.generate_json(...)`, and maps the decoded dict
onto the port's return type from `domain/agent.py`. None of them decide
pass/fail or aggregate anything themselves — see
[Domain model → Quality evaluation](domain-model.md#quality-evaluation-domainevalpy)
for where that logic actually lives.

`OllamaClient.generate_json` is deliberately lenient: it scans for the first
`{`/`[` in the raw response (local models routinely wrap JSON in prose or
code fences) and decodes with `strict=False` (local models routinely emit
literal newlines inside JSON string values). `OllamaClient.generate` also
caps `num_predict` so a model stuck repeating can't hang a pipeline run
indefinitely.

## Stub adapters (not yet implemented)

`ExecutorPort`/`AttesterPort` and their `NotImplementedError` stub adapters
exist purely so the seam described in OKF §10 (Attested Computation) is
ready — `AttestComputation` (the use case that would chain them) is written
and tested against fakes, but there is no real `Executor` (a thing that runs
a sanctioned computation and returns a `Receipt`) or `Attester` (deterministic,
no-LLM verification of a `Receipt` against a contract) wired up, because no
concept in the vault currently declares `type: Attested Computation`. Adding
one means writing real adapters for both ports and wiring them into
`Container` — the use case itself needs no changes.

## MCP server reuses the same wiring

`pipeline/mcp/server.py` does **not** construct its own adapters. It imports
`Container` from `cli.main` and builds one instance at module load, then
calls straight through to `container.search_concepts`,
`container.concept_repository`, and `container.metadata_repository` from its
tool functions. This guarantees the MCP server and the CLI are always backed
by the same vault, index, and models — see
[Reference → MCP server](../reference/mcp-server.md).

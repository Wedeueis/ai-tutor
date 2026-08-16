# CLI Reference

Entry point: `pipeline` (installed via `[project.scripts]` in
`pyproject.toml`, pointing at `pipeline.cli.main:app`). Run it via
`uv run pipeline <command>` or, inside an activated `.venv`, just
`pipeline <command>`. All commands read configuration from
`Settings.from_env()` — see [Configuration](configuration.md).

Every command builds a fresh `Container` (`cli/main.py::_container()`) — the
composition root that wires every concrete adapter to the use case it drives.

## `scan`

```bash
pipeline scan
```

Discovers new or changed files under `vault/raw/` and registers them in the
intake tracker (`ScanIntake`). Prints one line per newly discovered item:

```
discovered a1b2c3d4e5f6  raw_note  /path/to/vault/raw/my-note.md
```

Unchanged files (same content hash as already tracked) are silently skipped.
If a file's content changes and its previous intake item never got past
`discovered`/`error`, the stale row is deleted automatically — no manual
cleanup needed for a file you replace before it's ever parsed or ingested.
Run this before `parse-sources` or `ingest` — they only act on items already
discovered.

## `status`

```bash
pipeline status
```

Shows intake item counts grouped by `(state, kind)`, then lists every item
currently in `rejected` or `error` state with its path and error message —
the quickest way to see what needs attention.

## `prune`

```bash
pipeline prune
```

Deletes stale intake items: rows superseded by a later hash at the same path
that never got past `discovered`/`error` (e.g. you replaced a raw file
before `parse-sources`/`ingest` ever touched the old version). `scan` (above)
already stops new ones from accumulating going forward — `prune` cleans up
ones that predate that fix, or that piled up some other way. Items that were
actually `parsed`/`ingested`/`rejected` are never touched, even if later
superseded — that's audit history, not cruft. Prints one line per item
removed:

```
removed e3b0c44298fc  source_document  /path/to/vault/raw/report.pdf
```

## `retry <item-id>`

```bash
pipeline retry a1b2c3d4e5f6
```

Resets one intake item back to `discovered` (clearing any `error_message`),
so it re-enters the next `ingest`/`parse-sources` run. Use after fixing
whatever caused an `error` state (e.g. Ollama was down, a malformed file).

## `parse-sources`

```bash
pipeline parse-sources
```

Runs `scan` first, then `ParseSourceDocuments`: turns every discovered
`SOURCE_DOCUMENT` (PDF/PPTX/DOCX/XLSX/image) into markdown, captions any
extracted images, and splits the result into chunks — each becoming its own
intake item ready for `ingest`. Any chunk that looks like a garbled table
dump rather than prose (`domain/text_quality.py::looks_like_garbled_table` —
e.g. a mangled Docling table parse) is skipped instead of registered, so it
never reaches extraction; nothing is destroyed, the source document is
untouched in `vault/raw/`. Prints:

```
parsed a1b2c3d4e5f6  -> 4 chunk(s)
parsed 9f8e7d6c5b4a  -> 30 chunk(s), 3 skipped as garbled
```

No-op (with a message) if there are no source documents to parse. A document
that fails unexpectedly (a Docling error, an unreachable captioning model)
doesn't stop the rest of the batch — it's marked `error` and reported
separately, retryable via `pipeline retry <item-id>` (above) once fixed:

```
error parsing 9f8e7d6c5b4a  — <exception message>
```

## `ingest`

```bash
pipeline ingest
```

Runs `scan` first, then `IngestRawMaterial`: drives every unprocessed raw
note or chunk through the `KnowledgeAgent`, applies its create/merge
decisions to the vault, indexes whatever changed, and appends an entry to
the pipeline's SQLite audit log (see `pipeline log` below). Prints one line
per outcome:

```
created domains/coffee/cold-brew-coffee  (from raw/a1b2c3d4)
merged into domains/coffee/espresso-basics  (from raw/f00dbeef)
rejected raw/deadbeef01  — quality eval below threshold
```

Like `parse-sources`, an item that fails unexpectedly (Ollama unreachable, an
unparsable skill response) doesn't abort the batch — it's isolated, marked
`error`, and every other item still gets processed:

```
error raw/c0ffee01  — Ollama request to /api/generate failed after 4 attempt(s): ...
```

Set `LOG_LEVEL=DEBUG` (see [Configuration](configuration.md)) to see each
draft's domain classification, disambiguation confidence, and eval score as
`ingest` runs. See [Architecture → Data flow](../architecture/data-flow.md)
for exactly what happens inside this command.

## `validate <path>`

```bash
pipeline validate domains/coffee/cold-brew-coffee.md
pipeline validate domains/coffee/cold-brew-coffee   # .md suffix optional
```

Runs `ValidateConcept`: structural conformance (OKF §11) plus JSON Schema
validation against `pipeline/schemas/<Type>.schema.json` (or
`_base.schema.json` if no type-specific schema is registered). Exits `1` and
prints each issue if invalid:

```
domains/coffee/cold-brew-coffee: NOT conformant
  [status] unrecognized status 'archived' (expected draft|stable|deprecated, §5.4)
```

## `audit`

```bash
pipeline audit
```

Runs `AuditConceptQuality` over every content concept in the vault (`MOC`/
`Domain` types are skipped — they're structural, not knowledge to judge).
For each: a free, no-LLM check first
(`domain/text_quality.py::looks_like_garbled_table`) catches anything that's
obviously a mangled table dump; everything else goes through
`QualityAuditSkillPort.judge`, which asks a local model whether the body
genuinely stands alone as useful — this is what catches a *grammatically
fine but vacuous* fragment (e.g. "The following table represents a
collection of data points...") that lexical heuristics alone can't tell
apart from real prose. One LLM call per non-obviously-garbled concept, so
this scales with vault size. Purely a report — nothing is deleted. Prints:

```
value-ranges  — unusually numeric-dense (may be a bare data dump)
zero-values  — just restates that a data point has a given value
```

No-op (with a message) if nothing is flagged.

## `delete <path>`

```bash
pipeline delete data-points.md
pipeline delete data-points   # .md suffix optional
```

Removes one concept from the vault (`ConceptRepositoryPort.delete`) and its
metadata/vector index entries, and appends a `delete` entry to the SQLite
audit log. The actual cleanup action for anything `pipeline audit` flags —
`audit` and `delete` are deliberately separate commands, so removal is
always a distinct, explicit choice per concept rather than something `audit`
does automatically. Does **not** rewrite other concepts' `## Related`
sections that link to the deleted one — OKF §6 explicitly tolerates broken
links, and rewriting arbitrary other files as a side effect of a delete
would be a much bigger blast radius than the delete itself. Exits `1` if the
concept doesn't exist.

## `index`

```bash
pipeline index
```

Runs `RebuildIndex`: walks **every** concept in the vault and re-indexes it
(embeds + upserts into both the vector store and the metadata store). Use
after bulk manual edits to the vault, or to recover from a stale/corrupted
ChromaDB or SQLite metadata store — both are fully derivable from the vault's
markdown files. Prints the count:

```
indexed 12 concept(s)
```

## `new-domain <slug> --title ... --description ...`

```bash
pipeline new-domain observability \
  --title "Observability" \
  --description "Logging, metrics, and tracing practices."
```

Scaffolds a new `type: Domain` concept at `domains/<slug>.md`, appends a
creation entry to the audit log, and creates a placeholder eval-rubric file at
`pipeline/evals/domains/<slug>.json` (a single `"placeholder"` rubric you're
expected to replace with real, domain-specific quality criteria — see
[Onboarding → Add or change a domain's quality bar](../onboarding.md#add-or-change-a-domains-quality-bar)).
Fails with exit code `1` if the domain already exists. Doesn't link the new
domain from `Home.md` — that's a manual, curatorial step by design.

## `search <query> [-k N] [--type T] [--since DATE] [--until DATE]`

```bash
pipeline search "how long should cold brew steep" -k 3
pipeline search "" --type Decision --since 2026-05-01 --until 2026-05-31
```

Runs `SearchConcepts`. Pass `--type` (optionally with `--since`/`--until`,
ISO dates) to try a deterministic structured match first — e.g. every
`Decision` concept made in May — returned with `score=1.0`, skipping the
rest of the pipeline once there are enough hits (`SEARCH_STRUCTURED_MIN_RESULTS`).
Otherwise (or if the structured match comes up short): a two-stage hybrid
search — semantic (vector) and lexical (SQLite FTS5) results fused via
reciprocal rank fusion, then expanded/reranked through the concept link
graph — returning the `k` closest concepts (default `5`), most relevant
first. `score` is a fused rank-based number, not a raw cosine similarity —
see [Architecture → Data flow → Search](../architecture/data-flow.md#search):

```
0.033  domains/coffee/cold-brew-coffee
0.016  domains/coffee/ideal-espresso-ratio
0.008  domains/coffee/pourover-guide
```

## `categorize`

```bash
pipeline categorize
```

Backfills `## Categories` links for every concept that predates the Category
ontology layer (`CategorizeConcepts`) — skips anything already categorized,
without a `domain`, or of a structural type (`MOC`, `Domain`, `Source
Document`, `Category` itself). Runs the same `CategoryClassificationSkillPort`
classify-then-link logic `KnowledgeAgent` runs at ingest time, just across
the whole vault in one pass. New concepts get categorized automatically
during `pipeline ingest` — this command is only needed once, to catch up
content ingested before the feature existed (or after adding it to an
existing vault).

## `prerequisites [--limit N] [--dry-run]`

```bash
pipeline eval-prerequisites          # measure the gate FIRST
pipeline prerequisites --dry-run -n 5
pipeline prerequisites
```

Backfills `requires::` / `may_require::` edges for every concept that predates
the feature (`BackfillPrerequisites`) — skips anything already carrying an
edge, and anything of a structural type. New concepts get edges automatically
during `pipeline ingest`; this catches up what came before.

Unlike `categorize`, it does **not** skip concepts without a `domain`.
Prerequisites are not domain-scoped, and most of this vault has no domain — so
that guard would skip the backfill.

Idempotent, including for the inert tier: a concept already carrying a
`may_require::` edge is left alone rather than re-judged, so re-running never
quietly promotes an edge a human reviewed and left demoted.

**Measure before you run it.** The gate writes into the graph `tutor`'s study
plan walks, and a wrong `requires::` edge sends the learner to study something
they do not need with nothing downstream to catch it. `pipeline
eval-prerequisites` reports precision against the labelled gold set; the bar
is 0.9. On `llama3.1:8b` the gate scored 0.517, so this needs a cloud model —
see [configuration](configuration.md#choosing-a-chat-provider), and the
"when a cheap model underperforms" checklist there before considering a
pricier one.

A full pass is still hundreds of metered calls, which is what `--dry-run` and
`--limit` are for: `--dry-run -n 5` shows the edges it would write, with their
rolled-up scores, without touching the vault.

Two tiers are emitted. `requires::` is the only one any consumer reads;
`may_require::` is recorded for human review and is deliberately inert.

## `lineage <concept-id> [--relation-type T] [--direction D] [--max-hops N]`

```bash
pipeline lineage decisions/new-pricing --relation-type supersedes
```

Runs `TraceLineage`: walks typed-relation edges (a Dataview-style
`relation_type:: [[target]]` line in a concept's body — see CLAUDE.md's
"Typed relations" section) up to `--max-hops` away (default `3`),
`--direction` one of `outgoing`, `incoming`, or `both` (default). Prints
every path found — the full chain, not just whether one exists — e.g. to
answer "was this decision superseded, and by what, and was *that*
superseded too."

## `eval-prerequisites [--verbose]`

```bash
pipeline eval-prerequisites --verbose
```

Measures the prerequisite gate's precision against `evals/prerequisites-gold.json`,
a set of human-labelled pairs (`EvaluatePrerequisites`, RF1.3). Exits non-zero
below the 0.9 bar. Without it the gate is an LLM grading an LLM: the rubrics
are scored by the same model whose judgement they are meant to constrain.

Precision only. A wrong `requires::` edge sends the learner to study something
they do not need and nothing catches it; a missed one only costs the planner a
dependency it could have used. Recall is reported but never gated.

Each pair is judged exactly the way ingest judges one — same skill, same
rubrics, same threshold, same rollup — so the number measures the gate rather
than an approximation of it. A gate that emits nothing scores 0.0, not 1.0:
vacuous precision means the rubrics were never exercised.

**Gold-set entries read "source requires target"** — the dependent is stated
first, matching where the edge is written (see
[ADR 0002](../../../docs/adr/0002-prerequisite-edges-are-written-on-the-dependent-concept.md)).
A transposed set is not obviously wrong from its contents and has already cost
one full measurement cycle.

Two failure modes worth recognising in the output:

- **`ERR` rows** — the provider failed on that pair (a reasoning model
  returning empty content is the common one). Errored pairs are excluded from
  precision rather than counted as negatives, since an unmeasured pair says
  nothing about the rubrics.
- **`emitted as requires` close to `pairs`** — the gate is accepting nearly
  everything and has stopped discriminating, whatever its precision reads.

## `log [--limit N]`

```bash
pipeline log
```

Prints the pipeline's ingest audit trail (`BundleLogPort.list_entries()`) —
one `create`/`merge`/`reject` entry per decision made during `ingest` or
`new-domain`, newest first, up to `--limit` (default `20`). This is the
structured, queryable replacement for the old `vault/log.md` (WIKI_SPEC.md
§9): the pipeline stores it in SQLite instead of appending prose to the
bundle, since it's pipeline governance history, not vault content. See
[Architecture → Ports & adapters](../architecture/ports-and-adapters.md).

## `links <concept-id>`

```bash
pipeline links domains/coffee/qubits
```

Prints the outgoing and incoming §6 links for one concept
(`MetadataRepositoryPort.find_links`) — the cluster of related concepts
around it, independent of `tags`. Outgoing links come straight from the
concept's body; incoming links are everything in the vault that links back
to it.

## `mcp-serve [--host] [--port] [--stateless/--stateful]`

```bash
pipeline mcp-serve --host 127.0.0.1 --port 8000
```

Starts the MCP server (`pipeline.mcp.server`) over Streamable HTTP, plus a
`GET /health` readiness endpoint. See
[Reference → MCP server](mcp-server.md) for the tools/resources it exposes,
the health check, and optional auth.

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `$MCP_HOST` (`127.0.0.1`) | Bind address |
| `--port` | `$MCP_PORT` (`8000`) | Bind port |
| `--stateless` / `--stateful` | `$MCP_STATELESS` (stateless) | Whether the Streamable HTTP transport keeps no session state between requests (recommended for multi-replica deployments) or maintains a session per client |

Every flag falls back to its `Settings` value (see
[Configuration](configuration.md)) when omitted, so a deployment can be fully
configured via env vars / `.env` with no CLI flags at all. Auth
(`MCP_AUTH_TOKEN`) has no CLI flag — it's secret-shaped, so it's env-var-only
by design.

# PRD: AI Tutor

**Version:** 3.0
**Supersedes:** `PRD AI Tutor.md` (v2.0)
**Architecture:** Hexagonal (Ports & Adapters) + DDD
**Status:** ready to execute

> **How v3 differs from v2.** v2 was written before the architecture was
> settled and put every new file inside `src/pipeline/`. Fourteen decisions
> ([Wayfinding: AI Tutor PRD v3](https://github.com/Wedeueis/ai-tutor/issues/1))
> changed the component boundary, four of the five domain entities, and most
> of Epics 2–4. **Do not read v2 for anything but history.** Each section below
> links the decision that produced it; the ticket holds the reasoning, this
> document holds only the conclusion.
>
> Written in English for consistency with the decision record, `CONTEXT.md`,
> and `docs/adr/`, which v3 cross-references throughout.

---

## 1. Problem and solution

### 1.1 Context

This repo holds a knowledge vault (`vault/`), a local pipeline that produces
and serves it (`pipeline/`), and a read-only conversational agent over it
(`agent/`). The vault is written in the **Open Knowledge Format** — Google
Cloud's open, vendor-neutral markdown-plus-frontmatter standard, extended here
as `WIKI_SPEC.md` v0.2 (see §11). Retrieval works. What is missing is **learning**: nothing
tracks what the user knows, nothing schedules revision, nothing adapts how a
topic is taught, and nothing knows the user wants to go deep on some subjects
and stay shallow on others.

### 1.2 Solution

A new deployable, **`tutor/`**, that turns the vault into a stateful tutoring
system: it plans what to study from the vault's prerequisite graph, teaches
with a pedagogy chosen by subject, assesses, and schedules revision with FSRS
— keeping a durable record of every review.

### 1.3 What this is not

- Not a change to how `agent/` works.
- Not a multi-user system. **One learner** — there is no `user_id` anywhere.
- Not a hosted service. Local-first, with one planned relaxation
  ([Switch to OpenRouter for cloud models with reliable tool calling](https://github.com/Wedeueis/ai-tutor/issues/19)).

---

## 2. Component boundaries

> Decided in [Where does the tutor run — pipeline, agent, or a third deployable?](https://github.com/Wedeueis/ai-tutor/issues/2)

`tutor/` is a **fourth top-level deployable**, sibling to `pipeline/` and
`agent/`. It is not a package inside `pipeline/`, and every `src/pipeline/…`
path in v2 is wrong.

The governing premise: **`pipeline` and `tutor` must evolve on independent
cycles.** `pipeline`'s subject is knowledge — parsing, structuring, indexing,
and (planned) semantic-ontology modelling. A learner is not a knowledge
concept.

**Three rules:**

1. **MCP-only.** `tutor` reaches `pipeline` solely over its MCP server. No
   Python import, no shared virtualenv, no shared SQLite file.
2. **`pipeline` may grow new read tools, but never a learner-aware one.** Any
   new tool must make sense to *any* vault reader. **The word *learner* never
   appears in `pipeline`.**
3. **`agent/` is unchanged** — stateless, read-only — and is absorbed into
   `tutor/` as a retrieval sub-agent once `tutor`'s shape is proven. Until
   then ~70 lines of ADK wiring are duplicated, deliberately.

```
repo/
├── WIKI_SPEC.md
├── CONTEXT.md            ← ubiquitous language
├── docs/adr/             ← durable decisions
├── vault/                ← the OKF bundle (semantic memory)
├── pipeline/             ← produces + serves the vault
├── agent/                ← read-only retrieval agent
└── tutor/                ← NEW: the stateful tutor (episodic memory)
```

### 2.1 The memory boundary

> Decided in [May the tutor write to the vault?](https://github.com/Wedeueis/ai-tutor/issues/8); terms in `CONTEXT.md`

**The vault is semantic memory. `tutor` is episodic memory.** The test:
*would this make sense to someone who never took the session?*

`tutor` **never writes the OKF bundle.** It may write to the inbox
(`vault/raw/`), which is explicitly not part of the bundle:

| Discovery | Path |
|---|---|
| Coverage gap ("the vault never defines *ease factor*") | automatic → `vault/raw/inquiries/` |
| Contradiction between two concepts | automatic → `vault/raw/inquiries/` |
| New derived concept (a synthesis produced while teaching) | → `tutor/proposals/`, **awaiting human approval** |
| Learner blindspot ("you confuse X with Y") | **never leaves `tutor`** |

Approving a proposal is moving the file into `vault/raw/`. `pipeline` remains
the only thing that ever creates a concept.

> **Known shortcut.** Coverage gaps and contradictions are not really material
> to *ingest* — they are questions that deserve a research-and-synthesise
> flow `pipeline` does not have
> ([issue #15](https://github.com/Wedeueis/ai-tutor/issues/15)). They land in
> **`vault/raw/inquiries/`**, a dedicated folder that keeps them visibly
> distinct from material captured deliberately, gives that flow a defined
> place to read from when it lands, and lets ingest exclude them with one path
> rule rather than by inspecting content. See that folder's `README.md`.

---

## 3. Domain model

> `CONTEXT.md` is the ubiquitous language. This section is the model that
> implements it.

### 3.1 What v2 had, and what happened to it

| v2 entity | v3 |
|---|---|
| `Concept.prerequisites: List[Slug]` | **Removed** — prerequisites are typed relations in the link graph ([#4](https://github.com/Wedeueis/ai-tutor/issues/4)) |
| `StudyPlan` (stored DAG) | **Removed as an entity** — a projection, never persisted ([#4](https://github.com/Wedeueis/ai-tutor/issues/4)) |
| `LearnerModel(user_id, mastery_map, srs_map)` | **Removed as an aggregate** — the learner's state *is* the review log ([#9](https://github.com/Wedeueis/ai-tutor/issues/9), [#18](https://github.com/Wedeueis/ai-tutor/issues/18)) |
| `MasteryScore(value, confidence, …)` | **Removed** — mastery is a predicate over FSRS state ([#18](https://github.com/Wedeueis/ai-tutor/issues/18)) |
| `AssessmentItem` (entity) | **Removed as an entity** — ephemeral, generated per review ([#10](https://github.com/Wedeueis/ai-tutor/issues/10)) |
| `DomainType` (enum) | **Removed** — the vault's open-set `Domain` ontology is authoritative ([#5](https://github.com/Wedeueis/ai-tutor/issues/5)) |
| `SRSMetadata` (SM-2 shape) | **Replaced** — FSRS state, and it is derived, not authoritative ([#6](https://github.com/Wedeueis/ai-tutor/issues/6)) |

Very little of v2's model survives. That is the finding, not an oversight.

### 3.2 The v3 model

**Authoritative state** (`tutor`, in `learner.db`):

- **`ReviewEvent`** — append-only, the single source of truth. One row per
  review: `concept_id`, `rating` (1–4), `reviewed_at`, the algorithm identity
  and parameter set in force, and **the full exchange**: question asked,
  rubric used, learner's answer, resulting grade.
- **`DepthTarget`** — `category_id → level`. Learner-declared intent.
  **The only authoritative state that is not an event** and not rebuildable
  from events ([#20](https://github.com/Wedeueis/ai-tutor/issues/20)).

**Projections** (cached, checkpointed, rebuildable by replay):

- **`SchedulerState`** — FSRS state per **concept**: `stability`,
  `difficulty`, `due`, `last_review`, `state`, `step`.
- **`StudyPlan`** — a projection of *(prerequisite graph, review log, depth
  targets)*. Never stored.

**Value objects:**

- **`DepthLevel`** — `aware` | `working` | `specialist`. Each defines a
  **stability threshold expressed in days of interval** (never a bare float)
  and an **evidence requirement**.
- **`Rating`** — FSRS's 1–4 (Again / Hard / Good / Easy).

**Read from the vault over MCP** (never modelled locally as state): `Concept`,
`Domain`, `Category`, and `requires::` edges.

---

## 4. Functional requirements

### Epic 1 — `pipeline`: knowledge the tutor depends on

> This is the only work inside `pipeline`. `tutor` is not useful until it
> ships. It is all learner-agnostic, per rule 2.

| ID | Requirement | Notes |
|---|---|---|
| **RF1.1** | **Prerequisite emission at ingest** | Emit `requires:: [[/target]]` on the dependent concept. Two tiers ([#14](https://github.com/Wedeueis/ai-tutor/issues/14)): `requires::` (confident, the only tier the planner reads) and `may_require::` (uncertain — **recorded, inert, reviewable; it must stay inert**). Must work when `domain:` is absent, which is the common case. Must not introduce cycles; consumers must tolerate them regardless. |
| **RF1.2** | **Prerequisite quality gate** | Per-edge rubric gate reusing the existing rubric machinery and `aggregate_scores` rollup. Above threshold → `requires::`; below → `may_require::`. Rubrics must separate *prerequisite* from *related*: would a learner who does not know the target be **unable to follow** the source, not merely less enriched. |
| **RF1.3** | **Prerequisite gold set** | ~30 human-labelled pairs in `pipeline/evals/`, plus a command measuring precision against them. **Acceptance bar: ≥ 0.9 measured precision on the `requires::` tier**; recall unconstrained. Without this the gate is an LLM grading an LLM. |
| **RF1.4** | **Backfill command** | Emit prerequisites for concepts that predate the feature, mirroring `pipeline categorize`. |
| **RF1.5** | **Capture source credibility signals** | Populate `sources[].author` and `sources[].last_modified` at parse time. See [ADR 0001](../../adr/0001-capture-source-credibility-signals-never-store-a-score.md) — **capture at parse time or not at all**. `usage_count` stays unpopulated. |
| **RF1.6** | **`RelevanceCurator`** | Judges **fit to the bundle** — redundancy and on-topic-ness — which the existing intrinsic rubrics structurally cannot ([#7](https://github.com/Wedeueis/ai-tutor/issues/7)). Informed by credibility signals. **Absent signals mean *unknown*, which is neutral, never low** — otherwise it rejects the entire existing corpus and all hand-dropped notes. Its score is **not persisted**. Decision logic is pure domain; evidence gathering (embeddings, search) is a port. Origin is not an input: tutor-written inbox material is scored like anything else. |

**Out of Epic 1:** the new parser adapters from v2 (YouTube, Grobid, EPUB) —
separate effort, no unresolved architecture.

### Epic 2 — `tutor`: the harness

> Decided in [How is a pedagogy expressed, and how is a new one added?](https://github.com/Wedeueis/ai-tutor/issues/13).
> v2's RF2.1–RF2.5 are replaced: there is **one mechanism plus a set of
> directories**, not four pedagogies to implement.

| ID | Requirement | Notes |
|---|---|---|
| **RF2.1** | **Pedagogy as a `SKILL.md` directory** | agentskills.io shape: frontmatter (`name`, `description`, `allowed-tools`) + markdown body. Parsed with ADK's `load_skill_from_dir`. **The parser is reused; `SkillToolset`'s runtime discovery is not** — it failed outright locally ([#12](https://github.com/Wedeueis/ai-tutor/issues/12)), and discovery solves a problem `tutor` does not have. |
| **RF2.2** | **Deterministic selection by Domain** | The pedagogy follows the concept's `domain:` frontmatter — known *before* the model is invoked. `tutor` never classifies ([#5](https://github.com/Wedeueis/ai-tutor/issues/5)). |
| **RF2.3** | **Three-layer composition, invariants last** | Via `InstructionProvider` (`LlmAgent.instruction` accepts `Callable[[ReadonlyContext], str]`): (1) global `SOUL.md` — identity and base persona; (2) the pedagogy overlay; (3) **the invariant block, always last, never overridable**. |
| **RF2.4** | **The invariant block** | At minimum: ground strictly in vault content and never invent what it lacks; never write the bundle directly; never let episodic content cross into the vault; never claim mastery the review log does not support. |
| **RF2.5** | **Tool restriction, never injection** | `allowed-tools` enforced by a `ToolPredicate`. A pedagogy may **narrow** the shared read-only vault tools; it may **never add** one. No `MCPToolRegistry`. Code execution and diagram tools are out — capability and security decisions that must not ride in on a pedagogy file. |
| **RF2.6** | **The generic pedagogy** | Mandatory, and **the one that runs most often** — most concepts have no `domain:` (11 of 64 today). It is the default path, not a fallback afterthought. |
| **RF2.7** | **Volatile tier frozen at session start** | Mastery changes surface in the *next* session, never mid-dialogue. |

Adding a pedagogy = drop a directory + bind it to a Domain id. **No code
change, no deploy.**

### Epic 3 — `tutor`: planning

| ID | Requirement | Notes |
|---|---|---|
| **RF3.1** | **Study plan as a projection** | Projects *(prerequisite graph, review log, depth targets)*. Never stored. Reads `requires::` edges via `trace_lineage(relation_type="requires")` — **no new MCP tool needed**. |
| **RF3.2** | **`meets_target(concept, level)`** | Replaces v2's "Knowledge Tracing". Keyed on **stability**, not retrievability: stability moves only when you review, so a prerequisite satisfied in March stays satisfied in June. Retrievability decaying with time alone would reshuffle the plan with no new evidence ([#18](https://github.com/Wedeueis/ai-tutor/issues/18)). |
| **RF3.3** | **Depth targets per Category** | `aware` / `working` / `specialist`, bound to `type: Category` — the granularity that expresses "specialise in GraphRAG, stay aware of the rest of ML". **Untargeted Categories default to `aware`**: new Categories arrive from ingest unseen, and defaulting to depth would commit the learner to study they never chose. Needs a CLI or conversational way to set one, or the feature is unusable. |
| **RF3.4** | **Explore/exploit derived, not tuned** | Below target → exploit work, ordered by what is due. At/above target and unvisited on the frontier → explore work. A session fills from due-and-under-target first. **No ratio knob.** |
| **RF3.5** | *(v2's "re-routing")* | **Deleted as a feature.** A plan that is a projection re-routes by construction. Keep it as a *stated behaviour with a test*, so the property is intentional rather than accidental. |

### Epic 4 — `tutor`: assessment and scheduling

| ID | Requirement | Notes |
|---|---|---|
| **RF4.1** | **FSRS-6 in the domain layer** | Default parameters, **fuzzing disabled** (`py-fsrs` fuzzes by default via `random()`; disabling it also satisfies deterministic ordering). Contract: `calculate_next_review(state, rating, reviewed_at)` — **the timestamp is required**, elapsed time drives the stability update, so v2's two-argument signature cannot work. |
| **RF4.2** | **`py-fsrs` as a test-only differential oracle** | MIT-licensed, not a runtime dependency. FSRS's formulas are empirical — a reviewer cannot check them by reasoning, only by differential test. **This test is load-bearing, not optional.** (`fsrs-rs-python` has no declared license — avoid. Anki is AGPL — its SM-2 cannot be copied.) |
| **RF4.3** | **Ephemeral assessments, concept-keyed scheduling** | FSRS state is keyed by **concept id**. Each review generates a fresh question from the concept's *current* content, asks, grades, appends an event, discards the item. No card identity, no deduplication, no cache invalidation, nothing pedagogical persisted ([#10](https://github.com/Wedeueis/ai-tutor/issues/10)). |
| **RF4.4** | **Discursive grading → FSRS rating** | A rubric rollup maps to one of the four ratings and enters the same log. **The mapping must be deterministic and pure** — a domain function over an `EvalResult`, testable without an LLM. It must also record *that* a discursive review happened, which the `specialist` evidence requirement needs. |
| **RF4.5** | **Grading rubrics are `tutor`'s own** | `pipeline/evals/` rubrics score whether a *concept* is well-written; a learner's answer is a different subject. **Do not reuse them.** The `Rubric`/`RubricScore`/`EvalResult` *shape* is worth mirroring — but not importing (rule 1 forbids it). |

---

## 5. Contracts

```python
# tutor/src/tutor/domain/scheduling.py  — pure, no I/O, no dependencies
def calculate_next_review(
    state: SchedulerState, rating: Rating, reviewed_at: datetime
) -> SchedulerState: ...

def meets_target(state: SchedulerState, level: DepthLevel) -> bool:
    """Keyed on stability, not retrievability. See RF3.2."""
```

```python
# tutor/src/tutor/application/ports/outbound/vault.py
class VaultPort(Protocol):
    """The ONLY way tutor reaches the vault. MCP-backed, read-only."""
    def get_concept(self, concept_id: str) -> Concept: ...
    def search(self, query: str, k: int = 5) -> list[ConceptMatch]: ...
    def prerequisites(self, concept_id: str, max_hops: int = 3) -> list[Edge]: ...
```

```python
# tutor/src/tutor/application/ports/outbound/learner_store.py
class LearnerStorePort(Protocol):
    def append_review(self, event: ReviewEvent) -> None: ...
    def scheduler_state(self, concept_id: str) -> SchedulerState | None: ...
    def replay(self, concept_id: str | None = None) -> None: ...
    def depth_target(self, category_id: str) -> DepthLevel: ...
    def set_depth_target(self, category_id: str, level: DepthLevel) -> None: ...
```

```python
# tutor/src/tutor/application/harness.py
class HermesDomainOrchestrator:
    """A composition root, NOT a service holding prompt strings."""
    def for_concept(self, concept: Concept) -> tuple[InstructionProvider, ToolPredicate]: ...
```

Note there is no `user_id` in any signature.

---

## 6. Non-functional requirements

1. **Local-first.** Ollama + SQLite. One planned relaxation, deferred
   ([#19](https://github.com/Wedeueis/ai-tutor/issues/19)); PRD v3's obligation
   is only to keep the model provider behind a configurable seam.
2. **`llama3.1:8b` is not a safe default for any tool-calling path.** Measured:
   **0/6** real tool calls once the system prompt mentions tools, while
   `qwen3.5:4b` scored 6/6 on the same probe
   ([#12](https://github.com/Wedeueis/ai-tutor/issues/12)). It is currently the
   default in both `agent/` and `pipeline`.
3. **Tool-calling reliability is a per-model property, verified by sampling.**
   It is nondeterministic; a single passing run proves nothing.
4. **Grounding.** The tutor uses only vault content and the learner record.
   Enforced by the invariant block (RF2.4), not by convention.
5. **The semantic/episodic boundary is a guardrail**, listed here because it is
   the constraint most likely to be violated by a well-meaning later feature.
6. **`learner.db` is git-ignored.** It is a reading and failure history.
7. **Test coverage:** ≥ 85% on `domain` and `application`, with **no I/O mocks
   in the domain layer**. The domain layer has no dependencies to mock.
8. **Ingestion stays asynchronous** to any interactive surface.

---

## 7. Storage

> Decided in [Where does learner state live?](https://github.com/Wedeueis/ai-tutor/issues/9)

**Two SQLite files, both owned by `tutor`, neither shared with `pipeline`:**

- **`learner.db`** — review events, depth targets, projections, checkpoints.
- **ADK's session database** — conversation sessions, via
  `DatabaseSessionService`. **Separate on purpose**: ADK is pre-1.0 and its
  schema will churn; the review history is the one thing here that cannot be
  regenerated. (`require_confirmation`'s documented incompatibility with
  `DatabaseSessionService` no longer binds — the approval flow is filesystem-based.)

**Checkpoints.** Derived state is checkpointed so a rebuild replays only
events after the last checkpoint.

> **A checkpoint is valid only for the exact `(algorithm version, parameter
> set)` that produced it. Changing either invalidates every checkpoint and
> forces a full replay from the first event.** This must be enforced by
> storing that identity *on the checkpoint row* and comparing before use —
> never by remembering to clear a table. Stale-checkpoint reuse after a
> parameter re-fit silently corrupts scheduling. **This is an acceptance
> criterion, not a note.**

Scale, for context: replay is per-concept and off the read path. A heavy
user's decade is ~730k events (~35 MB); a full rebuild is seconds, one card is
milliseconds.

---

## 8. Roadmap

Atomic tasks. Each finishes and verifies before the next begins.

### Phase 0 — `pipeline` (blocks everything in `tutor`)

**Task 0.1 — Prerequisite emission with a two-tier gate**
- Create: prerequisite skill port + adapter; rubrics; wire into the ingest agent.
- Accept: emits `requires::` above threshold, `may_require::` below; works with
  `domain:` absent; introduces no cycles; both tiers land in `typed_links`.
- Verify: `cd pipeline && uv run pytest tests/domain/test_prerequisites.py`

**Task 0.2 — Gold set and precision measurement**
- Create: `pipeline/evals/prerequisites-gold.json` (~30 labelled pairs); a
  measurement command.
- Accept: reports precision on the `requires::` tier; **≥ 0.9 to ship**.
- Verify: `cd pipeline && uv run pipeline eval-prerequisites`

**Task 0.3 — Backfill command**
- Accept: emits prerequisites for pre-existing concepts; idempotent.
- Verify: `cd pipeline && uv run pytest tests/application/test_backfill_prerequisites.py`

**Task 0.4 — Capture source credibility signals**
- Modify: the parse path, to populate `sources[].author` / `last_modified`.
- Accept: signals populated where the document carries them; absent otherwise;
  no credibility *score* is ever written.
- Verify: `cd pipeline && uv run pytest tests/adapters/test_source_signals.py`

**Task 0.5 — `RelevanceCurator`**
- Create: domain service (pure decision logic) + evidence port.
- Accept: detects redundancy against the bundle; **absent credibility signals
  are neutral**; score not persisted; rejection path recorded in `bundle_log`.
- Verify: `cd pipeline && uv run pytest tests/domain/test_relevance_curator.py`

### Phase 1 — `tutor` skeleton and the learner store

**Task 1.1 — Scaffold the deployable**
- Create: `tutor/pyproject.toml` (own venv, **no `pipeline` dependency**),
  `tutor/src/tutor/{domain,application,adapters}/`, `.gitignore` for `learner.db`.
- Accept: `uv sync` succeeds; nothing imports `pipeline`.
- Verify: `cd tutor && uv run python -c "import tutor"`

**Task 1.2 — Event store and projections**
- Create: schema (`review_events` append-only, `depth_targets`,
  `scheduler_state`, `checkpoints`); `SqliteLearnerStore`.
- Accept: events are append-only; projections rebuild by replay; **a checkpoint
  whose `(algorithm, parameters)` differs is rejected and forces full replay**;
  `review_events` rows are independently interpretable (question and rubric
  stored as text, not as pointers).
- Verify: `cd tutor && uv run pytest tests/adapters/test_learner_store.py`

### Phase 2 — Scheduling

**Task 2.1 — FSRS-6 engine**
- Create: `tutor/src/tutor/domain/scheduling.py`, dependency-free.
- Accept: `calculate_next_review(state, rating, reviewed_at)`; fuzzing off;
  deterministic ordering of overdue items; **differential test against
  `py-fsrs` (test-only dependency)**.
- Verify: `cd tutor && uv run pytest tests/domain/test_scheduling.py`

**Task 2.2 — Depth levels and `meets_target`**
- Accept: three levels with thresholds **expressed in days**; `meets_target`
  keyed on **stability**; untargeted Category resolves to `aware`.
- Verify: `cd tutor && uv run pytest tests/domain/test_depth.py`

### Phase 3 — The harness

**Task 3.1 — Vault adapter (MCP)**
- Accept: implements `VaultPort` over the MCP server; read-only; no `pipeline` import.
- Verify: `cd tutor && uv run pytest tests/adapters/test_vault_mcp.py`

**Task 3.2 — Pedagogy loading and composition**
- Create: `tutor/pedagogies/<name>/SKILL.md` (generic + one example),
  `SOUL.md`, the invariant block, `HermesDomainOrchestrator`.
- Accept: correct pedagogy for a Domain; generic when unbound or absent;
  **the invariant block is present and LAST in every composition**; the
  `ToolPredicate` admits exactly the declared tools and never more.
- Verify: `cd tutor && uv run pytest tests/application/test_harness.py`

### Phase 4 — Planning

**Task 4.1 — Study plan projection**
- Accept: projects from *(graph, review log, depth targets)*; tolerates cycles
  (bounded by `max_hops`); ignores `may_require::`; **re-routes automatically
  when a prerequisite regresses — tested explicitly** (RF3.5).
- Verify: `cd tutor && uv run pytest tests/application/test_study_plan.py`

**Task 4.2 — Session composition and depth-target CLI**
- Accept: fills from due-and-under-target before advancing; a command sets a
  Category's depth target.
- Verify: `cd tutor && uv run pytest tests/application/test_session.py`

### Phase 5 — The teaching loop

**Task 5.1 — Assessment generation and grading**
- Accept: question generated from the concept's *current* content; nothing
  persisted but the event; **rubric rollup → rating is deterministic and pure**;
  discursive reviews are marked as such.
- Verify: `cd tutor && uv run pytest tests/application/test_review.py`

**Task 5.2 — ADK agent wiring**
- Accept: model configurable (**not `llama3.1:8b` by default**); tool calling
  verified by **sampled** runs, not one pass.
- Verify: `cd tutor && uv run pytest tests/test_agent.py`

**Task 5.3 — Inbox writes**
- Accept: coverage gaps and contradictions → `vault/raw/inquiries/`; derived concepts →
  `tutor/proposals/`; **blindspots never leave `learner.db`**; filename
  convention makes tutor-origin material legible in the inbox.
- Verify: `cd tutor && uv run pytest tests/application/test_contributions.py`

---

## 9. Suite verification

```bash
cd pipeline && uv run pytest --cov=src/pipeline && uv run mypy src/pipeline
cd tutor    && uv run pytest --cov=src/tutor    && uv run mypy src/tutor
```

---

## 10. Deferred, deliberately

| Ambition | Issue |
|---|---|
| Research-and-synthesise flow in `pipeline` | [#15](https://github.com/Wedeueis/ai-tutor/issues/15) |
| Source discovery and credibility-weighted prioritisation | [#16](https://github.com/Wedeueis/ai-tutor/issues/16) |
| Usage-driven forgetting; cross-learner ranking layer | [#17](https://github.com/Wedeueis/ai-tutor/issues/17) |
| OpenRouter / cloud models | [#19](https://github.com/Wedeueis/ai-tutor/issues/19) |
| Adaptive explore/exploit balancing | [#21](https://github.com/Wedeueis/ai-tutor/issues/21) |
| Multi-learner support; improving `pipeline`'s domain classification; new parser adapters (RF1.1–1.3 of v2) | Out of scope on [#1](https://github.com/Wedeueis/ai-tutor/issues/1) |

---

## 11. Provenance of the two names

**OKF — the Open Knowledge *Format*.** An open specification published by
Google Cloud's Data Cloud team (v0.1, June 2026): "a vendor-neutral, agent-
and human-friendly standard for representing the metadata, context, and
curated knowledge that modern AI systems need," representing knowledge as a
directory of markdown files with YAML frontmatter.
([announcement](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing))

This repo's `WIKI_SPEC.md` is **v0.2 of that format** — the same standard,
extended. Vendor-neutrality is the point: nothing here requires a Google
account, SDK, or service. v2 called it a "Framework"; the only correction is
the word.

**Hermes — a real agent harness, used as an architecture reference.**
[hermes-agent.org](https://hermes-agent.org/), by Nous Research, MIT-licensed.
Its architecture is the reference for `tutor`'s harness; **ADK remains the
runtime**, and Hermes is not a dependency.

What v3 takes from it:

- **Automated skill creation targeting the agentskills.io standard** — the
  same standard RF2.1 adopts for pedagogy directories. This is why keeping the
  `SKILL.md` shape matters even though `SkillToolset`'s runtime discovery is
  not used: a pedagogy stays loadable by Hermes-compatible tooling.
- **Persistent memory across sessions** — `tutor`'s episodic store is the same
  idea, made specific: an append-only review log rather than general
  conversational memory.
- **Layered identity with a session overlay** — the shape RF2.3 implements as
  `SOUL.md` + pedagogy overlay, with the invariant block added on top as
  something Hermes does not have.

What v3 does not take: the multi-platform gateway, the execution environments,
and the MLOps/training infrastructure — all outside this system's scope.

Hermes' harness is deliberately general, so it carries nothing pedagogical or
domain-typed; those parts are ours to design
([#3](https://github.com/Wedeueis/ai-tutor/issues/3)).

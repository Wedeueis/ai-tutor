# tutor

The stateful AI Tutor: it plans what to study from the vault's prerequisite
graph, teaches with a pedagogy chosen by subject, assesses, and schedules
revision with FSRS — keeping a durable record of every review.

A fourth top-level deployable, sibling to `pipeline/` and `agent/`. See
`docs/projeto/PRDs/PRD AI Tutor v3.md` for the full specification and
`CONTEXT.md` for the ubiquitous language.

## The two rules that shape everything here

**1. `tutor` reads the vault only over MCP.** No `import pipeline`, no shared
virtualenv, no shared SQLite file. `pipeline`'s subject is knowledge; a learner
is not a knowledge concept, and the two must evolve on independent cycles.
`make check-boundary` enforces this.

**2. The vault is semantic memory; `tutor` is episodic memory.** The test:
*would this make sense to someone who never took the session?* Yes means it may
live in the vault, no means it never leaves here.

| Discovery | Where it goes |
|---|---|
| Coverage gap ("the vault never defines *ease factor*") | automatic → `vault/raw/inquiries/` |
| Contradiction between two concepts | automatic → `vault/raw/inquiries/` |
| A new derived concept produced while teaching | `tutor/proposals/`, awaiting human approval |
| A learner blindspot ("you confuse X with Y") | **never leaves `learner.db`** |

`tutor` never writes the OKF bundle. `pipeline` remains the only thing that
creates a concept; approving a proposal means moving the file into
`vault/raw/` — see `proposals/README.md`.

The enforcement is `ContributionPort`, which has exactly two verbs and no type
for a blindspot. A guard that inspected content and decided could be wrong; a
verb that does not exist cannot be called. Everything it writes is named
`<date>-tutor-<kind>-<slug>.md`, so tutor-origin material is obvious in an
inbox otherwise full of things you dropped there yourself.

## Layout

```
src/tutor/
├── domain/                      pure, no I/O, nothing to mock
├── application/ports/outbound/  the seams: VaultPort, LearnerStorePort
└── adapters/                    sqlite/ (learner.db), mcp/ (the vault)
```

## Using it

```bash
uv run tutor depth set categories/graph-rag specialist
uv run tutor depth show                 # only what was actually declared
uv run tutor depth show categories/x    # ...and whether it was ever declared

uv run tutor plan /concepts/attention      # needs pipeline's MCP server
uv run tutor session /concepts/attention   # one sitting's worth of it
```

A depth target is bound to a **Category**, which is the granularity that
expresses "specialise in GraphRAG, stay aware of the rest of ML". A Category
nobody has targeted answers `aware` — the default is deliberate, not a
placeholder: new Categories arrive from ingest unseen, and defaulting to depth
would commit the learner to study they never chose.

The plan is **never stored**. It is projected from *(prerequisite graph, review
log, depth targets)* each time you ask, which is why it re-routes on its own: a
prerequisite answered badly is simply under target again the next time it is
built. There is nothing to invalidate.

## State

Two SQLite files, both owned by `tutor`:

- **`learner.db`** — `review_events` (append-only, authoritative), depth
  targets, and the projections rebuilt from them. Git-ignored: it is a reading
  and failure history, not source.
- **ADK's session database** — conversation sessions. Separate on purpose: ADK
  is pre-1.0 and its schema will churn, while the review history is the one
  thing here that cannot be regenerated.

A checkpoint is valid only for the exact `(algorithm version, parameter set)`
that produced it. Changing either invalidates every checkpoint and forces a
full replay from the first event.

## Development

```bash
uv sync
make test            # fast tests
make typecheck
make check-boundary  # nothing imports pipeline
make coverage
```

Integration tests need Ollama running locally and `pipeline`'s MCP server
(`cd ../pipeline && uv run pipeline mcp-serve`).

**Do not default to `llama3.1:8b`.** Measured at 0/6 real tool calls once the
system prompt mentions tools, against 6/6 for `qwen3.5:4b` on the same probe
(issue #12). Every teaching turn is a tool-calling path.

`tests/test_agent.py` carries a **sampled** probe for exactly this, because a
single passing run proves nothing about a nondeterministic property:

```bash
uv run pytest -m integration tests/test_agent.py     # needs Ollama + the MCP server
TUTOR_PROBE_SAMPLES=12 uv run pytest -m integration tests/test_agent.py
```

## The model

One environment variable, because that is the whole of the provider seam:

```bash
TUTOR_CHAT_MODEL=qwen3.5:4b                         # local (the default)
TUTOR_CHAT_MODEL=openrouter/deepseek/deepseek-chat  # hosted, no code change
```

A bare name is local and gets Ollama's `ollama_chat/` prefix; anything already
naming a provider passes through untouched and is not pointed at localhost.

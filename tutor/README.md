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
`vault/raw/`.

## Layout

```
src/tutor/
├── domain/                      pure, no I/O, nothing to mock
├── application/ports/outbound/  the seams: VaultPort, LearnerStorePort
└── adapters/                    sqlite/ (learner.db), mcp/ (the vault)
```

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

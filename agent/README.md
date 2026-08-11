# Knowledge Retrieval Agent

A conversational [Google ADK](https://github.com/google/adk-python) agent that
answers questions grounded in the OKF vault (`../vault/`), by calling
`pipeline`'s existing MCP server as its sole tool source. Read-only: no
write-back, no external tool-calling (email, etc.) — see "Why this shape"
below for why that scope was deliberately cut from the original design.

This is the fourth top-level component in this repo, alongside `WIKI_SPEC.md`,
`vault/`, and `pipeline/` — a separate deployable, not a change to anything
inside `pipeline/`. It only *depends on* `pipeline`'s MCP server being
reachable; it doesn't share code or a virtualenv with it.

## Setup

Requires `pipeline`'s MCP server running (`cd ../pipeline && uv run pipeline
mcp-serve`) and Ollama running locally with a chat-capable model pulled (the
same `OLLAMA_HOST`/`OLLAMA_CHAT_MODEL` `pipeline` itself uses — default
`llama3.1:8b`).

```bash
cd agent
uv sync
uv run adk web       # interactive dev UI, http://localhost:8000
# or:
uv run adk run knowledge_retrieval_agent   # terminal chat
```

Env vars (all optional, all default to `pipeline`'s own defaults):

| Var | Default | |
|---|---|---|
| `OLLAMA_CHAT_MODEL` | `llama3.1:8b` | Local model, via LiteLlm's `ollama_chat/<model>` (not `ollama/<model>` — that form has documented tool-loop/context bugs in LiteLlm's Ollama integration). |
| `OLLAMA_HOST` | `http://localhost:11434` | |
| `PIPELINE_MCP_URL` | `http://127.0.0.1:8000/mcp` | The pipeline MCP server's Streamable HTTP endpoint (`/mcp` is `MCPServer`'s default mount path). |

Verified working end-to-end against a real local Ollama + `pipeline
mcp-serve` during development (`google-adk==2.6.3`) — see "A pinning note"
below for one dependency gotcha that came up doing that.

## Design

`knowledge_retrieval_agent/agent.py` is intentionally small: one `LlmAgent`,
one `McpToolset` pointed at `pipeline`'s MCP server
(`StreamableHTTPConnectionParams`), one system instruction describing when to
reach for which read-only tool (structured search vs. hybrid search vs.
lineage tracing vs. source grounding). All the actual retrieval logic —
hybrid search, graph expansion, typed-relation traversal — lives in
`pipeline`; this agent only decides *which* tool to call and *how to phrase
an answer* from what comes back.

### Why this shape

The original scenario this was scoped from ("PM agent," see the plan history
for this repo) also wanted write-back (agent-proposed vault changes with
human confirmation) and external tool-calling (email search/send). Both were
cut from this component's scope on purpose: **this platform needs a
Knowledge Retrieval Agent, not a PM agent** — the write-back/governance loop
and email integration were illustrative of what the vault's ontology *could*
support, not a requirement for this piece. If that's wanted later, two ADK
constraints are worth knowing going in (true as of `google-adk==2.6.3`,
worth re-checking since this is a fast-moving, pre-1.0-grade project):

- `require_confirmation` (the propose → wait-for-approval → execute
  mechanism) is documented as **experimental**, and is **incompatible with
  `DatabaseSessionService`/`VertexAiSessionService`** — only
  `InMemorySessionService` reliably supports it, which is in tension with
  wanting a durable audit trail of confirmed actions.
- Open `google/adk-python` issues report `require_confirmation` doesn't yet
  reliably gate tools sourced via `McpToolset` (only native `FunctionTool`s)
  — a write-back tool would likely need to be a local `FunctionTool` proxy
  rather than exposed directly through the MCP server.

### A pinning note

`google-adk` (as of `2.6.3`) imports names from the `mcp` package (Anthropic's
MCP Python SDK) that don't exist in `mcp==2.0.0` (a breaking release) — it
needs `mcp<2.0.0`. `pyproject.toml` pins accordingly
(`mcp>=1.9.0,<2.0.0`). If `uv sync` ever fails with `ModuleNotFoundError:
No module named 'mcp.shared.session'` (or similar), this is why — check
whether `google-adk` has caught up to `mcp` 2.x before loosening the pin.

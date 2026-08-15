# What to borrow from the Hermes agent harness

Research note for [issue #3](https://github.com/Wedeueis/ai-tutor/issues/3) (map: [#1](https://github.com/Wedeueis/ai-tutor/issues/1)).
Date: 2026-08-15. Branch: `research/hermes-harness`.

**Standing constraint**: Google ADK (`google-adk`, currently `2.6.3` in `agent/`) stays the runtime.
Hermes is an architecture reference only — not a dependency to adopt.

---

## 1. Bottom line

1. **A thing called "Hermes Agent" that is genuinely an agent harness does exist**, and it is
   plausibly what PRD v2 means: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent),
   MIT-licensed, docs at <https://hermes-agent.nousresearch.com/docs>. It is *not* the Hermes
   **models** (Nous Research's fine-tuned LLM line) — the docs are explicit that the harness is
   "model-agnostic … distinct from the Hermes LLM line that shares the name."
2. **But the PRD is almost certainly name-dropping, not citing.** See §2 — there is nothing in
   Hermes Agent about pedagogy, domain-typed personas, or tutoring. "Hermes Agent Harness" as the
   PRD uses it (a component that "instantiates" per-domain pedagogical strategies) does not exist
   under that name anywhere. What exists is a general-purpose personal-assistant harness whose
   *mechanisms* happen to be a good reference for persona/tool/state injection.
3. **Most of what is worth borrowing, ADK already ships.** ADK 2.6.3 implements the same
   [Agent Skills](https://agentskills.io/specification) standard Hermes skills use
   (`google.adk.tools.skill_toolset.SkillToolset`), plus dynamic instructions, context-aware tool
   filtering, scoped session state, and a plugin/callback system with the same hook shape as
   Hermes' plugin hooks. The genuinely borrowable parts are **three design ideas**, not code:
   layered prompt assembly with a frozen volatile tier, progressive disclosure of pedagogy as
   skills, and per-context tool gating.
4. **Recommendation**: keep the *name* `HermesDomainOrchestrator` only if the team wants it as a
   nod; architecturally it should be a thin ADK-native composition (instruction provider +
   `SkillToolset` + `tool_filter` predicate + session state), **not** a hand-rolled orchestrator.
   Concrete shape in §5.

---

## 2. Disambiguation: which Hermes?

| Candidate | What it is | Fits "agent harness that injects per-domain pedagogical personas and tools"? |
|---|---|---|
| **Nous Research Hermes models** (Hermes 2/3/4, `NousResearch/*` on HF) | Fine-tuned open-weight LLMs | No. A model, not a harness. |
| **Nous Research Hermes Agent** | Open-source (MIT) agent harness / personal assistant runtime — [repo](https://github.com/NousResearch/hermes-agent), [docs](https://hermes-agent.nousresearch.com/docs) | **Partially.** It is a real harness with persona, skill, tool and memory injection. Nothing pedagogical, nothing domain-typed. |
| **Any "Hermes" tutoring harness** | — | **Does not exist.** No primary source found. |

### Evidence the PRD is not citing a real artifact

- The same PRD's §1.1 calls OKF "o padrão Open Knowledge Framework (OKF) **da Google**"
  (`docs/projeto/PRDs/PRD AI Tutor.md:11`). That is false — OKF is defined by this repo's own
  `WIKI_SPEC.md` and is not a Google standard. A document that misattributes the format it is
  built on is a document that name-drops.
- The PRD's `HermesDomainOrchestrator` is specified as a **domain service in the hexagon**
  (`src/pipeline/domain/services/hermes_orchestrator.py`) selecting prompt guidelines by
  `DomainType`. Hermes Agent has no such concept: its identity layer is a single `SOUL.md` per
  `HERMES_HOME`, and switching identity is a *session overlay* (`/personality <name>`), not a
  typed dispatch.

**So**: read "Hermes Agent Harness" in the PRD as *"a harness in the Hermes Agent sense"* — a
structural inspiration. Do not go looking for an API to conform to. If PRD v3 keeps the name, it
should carry a one-line footnote saying exactly that, otherwise the next reader will burn the same
afternoon.

---

## 3. What Hermes Agent is, architecturally

All claims below from Hermes' own docs/source.

### 3.1 One agent class, many entry points

A single `AIAgent` class in `run_agent.py` is driven by `cli.py` (terminal), `gateway/run.py`
(messaging platforms) and `acp_adapter/` (IDE). "One AIAgent class serves CLI, gateway, ACP, batch,
and API server. Platform differences live in the entry point, not the agent."
([architecture](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture),
[source](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/developer-guide/architecture.md))

The loop is: prompt construction (`agent/prompt_builder.py`) → provider resolution
(`hermes_cli/runtime_provider.py`) → API call → tool dispatch → persistence to SQLite; repeat until
no tool calls remain.

### 3.2 Persona/strategy injection = a three-tier, cache-aware system prompt

The single most transferable idea. From
[Prompt Assembly](https://hermes-agent.nousresearch.com/docs/developer-guide/prompt-assembly)
(`agent/system_prompt.py`):

| Tier | Contents | Volatility |
|---|---|---|
| **Stable** | Agent identity (`SOUL.md`), tool/model guidance, skills prompt, environment + platform hints | Never changes → anchors the cached prefix |
| **Context** | Caller-supplied system messages; **first matching** project context file: `.hermes.md`/`HERMES.md` → `AGENTS.md` → `CLAUDE.md` → `.cursorrules` | Per project |
| **Volatile** | Memory snapshot (`MEMORY.md`), user profile (`USER.md`), external memory blocks, timestamp/session/model metadata | Per session, **frozen at session start** |

Two rules make this more than layering:

- **The volatile tier is a frozen snapshot.** Memory written mid-session updates disk but does *not*
  rebuild the cached prompt until a new session or explicit invalidation. Rationale, quoted:
  "This is one of the most important design choices in the project because it affects: token usage,
  prompt caching effectiveness, session continuity, memory correctness."
  ([memory docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory) describe the
  same block rendered with a usage meter, e.g. `67% — 1,474/2,200 chars`.)
- **Ephemeral things stay out of the system prompt entirely**: `ephemeral_system_prompt`, prefills,
  gateway overlays, and `pre_llm_call` plugin context are appended to the *user* message instead,
  "to keep the stable prefix stable for caching."

Identity itself: `SOUL.md` at `~/.hermes/SOUL.md` (loaded **only** from `HERMES_HOME`, never CWD),
goes into "slot #1 of the system prompt," after prompt-injection scanning and truncation. Temporary
tone shifts are a session overlay via `/personality <name>` (built-ins include `teacher`), cancelled
with `/personality none`.
([personality](https://hermes-agent.nousresearch.com/docs/user-guide/features/personality))

### 3.3 Strategy-as-content: skills with progressive disclosure

Hermes skills are directories with a `SKILL.md` (YAML frontmatter + markdown body) living under
`~/.hermes/skills/<category>/<skill>/`, compatible with the open
[agentskills.io](https://agentskills.io/specification) standard.
([skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills))

Loading is three-level:

- **L0** `skills_list()` → metadata only (~3k tokens)
- **L1** `skill_view(name)` → full `SKILL.md`
- **L2** `skill_view(name, path)` → a specific reference file

Frontmatter carries conditional-activation metadata under `metadata.hermes`, notably
`requires_toolsets` and `fallback_for_toolsets`, plus `platforms` OS restrictions and
`required_environment_variables`.

Skills are also **written by the agent** (`skill_manage` tool: `create`/`patch`/`edit`/`delete`),
optionally behind an approval gate (`skills.write_approval: true`, reviewed via
`/skills pending|diff|approve|reject`). The docs draw the division of labour cleanly: "memory stores
small durable facts that should always be in context, while skills store longer procedures that
should load only when relevant."

### 3.4 Tool registration: a decentralised import-time registry + toolsets

`tools/registry.py` "has no deps — imported by all tool files"; each tool module calls
`registry.register()` at import. ~70 tools across ~28 toolsets. Dispatch via
`model_tools.handle_function_call()`, which resolves the name, checks availability (gating) and
executes. ([architecture](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture))

Tools are grouped into **toolsets** "that can be enabled or disabled per platform"
(`hermes chat --toolsets "web,terminal"`, or `~/.hermes/config.yaml`), with gating on credentials
(e.g. X Search gated on `XAI_API_KEY`, off by default).
([tools](https://hermes-agent.nousresearch.com/docs/user-guide/features/tools))

MCP servers are declared in `config.yaml` under `mcp_servers` (stdio `command`/`args`, or HTTP
`url`/`headers`), registered as `mcp_<server>_<tool>`, with **per-server allow/deny lists** and glob
support: ([mcp](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp))

```yaml
mcp_servers:
  github:
    tools:
      include: [create_issue, list_issues]
  stripe:
    tools:
      exclude: [delete_customer]
```

### 3.5 Session state

`hermes_state.py` — a SQLite session/state DB with FTS5 full-text search, session lineage
(parent/child across context compressions), per-platform isolation, atomic writes.
`agent/context_compressor.py` does lossy summarisation past a token budget. A `session_search` tool
lets the agent query its own past conversations (`~/.hermes/state.db`), returning raw messages.

### 3.6 Interception: plugin/event hooks

Plugins are discovered from `~/.hermes/plugins/`, `.hermes/plugins/` and pip entry points, managed
by `PluginManager` in `hermes_cli/plugins.py`. Hooks are classified by power
([hooks](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks)):

- **Control/directive** (can block or reshape): `pre_tool_call`, `pre_llm_call`, `pre_verify`,
  `pre_gateway_dispatch`
- **Transform** (replace content): `transform_tool_result`, `transform_terminal_output`,
  `transform_llm_output`, `transform_api_error_classification`
- **Observer**: `post_tool_call`, `post_llm_call`, `on_session_start`, `on_session_end`,
  `on_skill_lifecycle`, `subagent_start`, `subagent_stop`

Design principle worth stealing verbatim: "Hook callback errors are isolated and logged rather than
crashing the agent." Shell hooks additionally support `fail_closed: true` for security gates.

> **Maturity caveat, from the horse's mouth.** Hermes shipped four of these hooks documented but
> never invoked — [issue #2817](https://github.com/NousResearch/hermes-agent/issues/2817) reports
> `pre_llm_call`, `post_llm_call`, `on_session_start`, `on_session_end` were in `VALID_HOOKS` and in
> the docs but never called; only `pre_tool_call`/`post_tool_call` were wired. Fixed by
> [PR #3542](https://github.com/NousResearch/hermes-agent/pull/3542) (merged 2026-03-28). Treat
> Hermes docs as a design catalogue, not a proven-behaviour reference.

---

## 4. Mapping onto ADK primitives

Verified against the installed `google-adk==2.6.3` in `agent/.venv/` and adk.dev docs.

| Hermes mechanism | ADK equivalent | Verdict |
|---|---|---|
| `SOUL.md` in stable tier (slot #1) | `LlmAgent.instruction` — `Union[str, InstructionProvider]`, where `InstructionProvider = Callable[[ReadonlyContext], Union[str, Awaitable[str]]]` (`google/adk/utils/instructions_utils.py:37`) | **Free.** A callable instruction *is* per-invocation persona assembly. |
| Templated state in prompt | `{var}` / `{var?}` / `{artifact.var}` interpolation, `inject_session_state()` ([llm-agents](https://adk.dev/agents/llm-agents/)) | **Free.** |
| Cross-agent shared prefix (`global_instruction`) | `GlobalInstructionPlugin` (`global_instruction` param deprecated) | **Free**, but prefer the plugin. |
| Three-tier stable/context/volatile ordering + frozen snapshot | **Nothing.** ADK gives you one `instruction` string and no caching contract over its layers. | **Borrow the discipline** (§5.1). |
| Skills: `SKILL.md`, L0/L1/L2 progressive disclosure | `google.adk.tools.skill_toolset.SkillToolset` + `google.adk.skills.{models,prompt,skill_registry}`, generating `list_skills` / `load_skill` / `load_skill_resource` / `run_skill_script`; same agentskills.io spec ([adk.dev/skills](https://adk.dev/skills/)) | **Free — and this is the headline.** Don't hand-roll pedagogy loading. |
| Skill metadata gating (`requires_toolsets`) | `Frontmatter.metadata` is `extra="allow"`; ADK reads `adk_additional_tools` and `adk_inject_state: true` (state interpolation into the SKILL.md body) — `google/adk/skills/models.py` | **Free**, with an ADK-flavoured key. |
| Dynamic skill discovery from a store | `SkillRegistry` ABC (`get_skill`, `search_skills`, `search_tool_description`) → `search_skills` tool | **Free.** Natural seam onto the vault/MCP. |
| Tool registry (import-time self-registration) | ADK has no global registry; tools are passed per-agent in `LlmAgent(tools=[...])` | **Do not copy.** A process-global registry fights ADK's explicit composition and is worse for testing. |
| Toolsets enabled per platform; MCP `include`/`exclude` | `BaseToolset(tool_filter=...)`, accepting a `list[str]` **or** a `ToolPredicate` — `Callable[[BaseTool, Optional[ReadonlyContext]], bool]`, applied per `get_tools(readonly_context)` call (`google/adk/tools/base_toolset.py:194-205`, `tools/mcp_tool/mcp_toolset.py:385`) | **Free, and strictly better** — the predicate sees `ReadonlyContext`, so the exposed toolset can vary *per invocation from session state*. This is RF2.5 ("injeção dinâmica de ferramentas MCP conforme o domínio da sessão") already solved. |
| SQLite session DB, per-platform isolation | `DatabaseSessionService`; state scope prefixes `user:` / `app:` / `temp:`; writes only via `output_key`, `EventActions.state_delta`, or `CallbackContext`/`ToolContext.state` ([sessions/state](https://adk.dev/sessions/state/)) | **Free.** |
| `session_search` over past conversations (FTS5) | Not equivalent. ADK's `MemoryService` is a different abstraction; there is no built-in FTS over prior sessions. | **Gap** — but the tutor's cross-session recall should be the *learner model*, not chat search (§5.4). |
| Context compression at token budget | `ContextFilterPlugin` (`google/adk/plugins/context_filter_plugin.py`); no lossy summariser out of the box | Partial. |
| Plugin hooks (control / transform / observer) | `BasePlugin` (`google/adk/plugins/base_plugin.py`) with `before/after_{agent,model,tool}_callback`, `on_{model,tool,agent,run}_error_callback`, `on_user_message_callback`, `before/after_run_callback`, `on_event_callback`; plus per-agent `before_tool_callback` etc. on `LlmAgent` | **Free, and more complete than Hermes'.** ADK has app-wide (plugin) *and* per-agent (callback) levels. |
| `pre_llm_call` context injection into the user message | `before_model_callback` mutating `LlmRequest` | **Free.** |
| Per-domain agents | ADK sub-agents + `SequentialAgent`/`ParallelAgent`/`LoopAgent` | Free; see §5.2 for why you probably want *one* agent, not three. |

---

## 5. What to actually borrow — concrete recommendations

### 5.1 Borrow the tiering discipline, implement it as one `InstructionProvider`

Do **not** build a `HermesDomainOrchestrator` that concatenates strings ad hoc. Build one async
instruction provider that assembles, in fixed order:

1. **Stable**: tutor identity + grounding rules + "how to use the vault tools" — identical for every
   domain and every session. This is the prefix you want cacheable.
2. **Context**: the `DomainType` pedagogical stance (PBL / process-diagram / Socratic). Changes per
   session, not per turn.
3. **Volatile**: a *frozen-at-session-start* snapshot of the learner model — current
   `MasteryScore`s for the plan's frontier, due SRS items, last session's outcome.

Freeze rule, copied from Hermes: mastery updated mid-session must **not** rewrite the system prompt
mid-session. It lands in session state and shows up next session. Rationale is Hermes' own —
caching, session continuity, and memory correctness — and it also removes a class of bug where the
tutor's view of the learner shifts under it mid-dialogue.

ADK gives you the mechanism for free (`instruction=my_provider`, `inject_session_state`); what
Hermes gives you is the *rule about what belongs in which layer*. That rule is the deliverable.

### 5.2 Model each pedagogy as a Skill, not as a branch in an orchestrator

RF2.1–RF2.4 currently read as `if domain == BIOLOGY: prompt = ...`. Don't. ADK ships the
agentskills.io implementation; a pedagogy is exactly what a `SKILL.md` is for — a procedure loaded
only when relevant.

```
skills/
  pbl-debugging/SKILL.md        # RF2.2 SOFTWARE_ENGINEERING
  process-mapping/SKILL.md      # RF2.3 BIOLOGY  (+ assets/mermaid templates)
  socratic-dialogue/SKILL.md    # RF2.4 HUMANITIES
```

Wired as `SkillToolset(skills=[...], additional_tools=[...])`. Why this beats a domain service:

- **The "adding a fourth pedagogy" open question in the map answers itself**: drop a directory. No
  code change, no new enum branch, no redeploy of the orchestrator.
- **Progressive disclosure**: L0 costs ~100 tokens of frontmatter per pedagogy; the full strategy
  body only enters context when the session actually engages it.
- `metadata.adk_inject_state: true` lets a SKILL.md body interpolate `{current_concept}` /
  `{mastery?}` from session state — pedagogy templates parameterised by the learner model, with no
  glue code.
- `additional_tools` attaches strategy-specific tools (Mermaid renderer for process-mapping, code
  runner for PBL) to the skill that needs them, which is exactly RF2.2/RF2.3's intent.

**Caveat**: `SkillToolset` is **experimental** in ADK (feature flag `SKILL_TOOLSET` in
`google/adk/features/_feature_registry.py:62`; adk.dev marks skills experimental across Python
v1.25.0, TS v0.6.1, Go v1.2.0). Design the pedagogy content as plain `SKILL.md` directories — that
much is a published open standard and survives regardless — and treat the ADK loader as replaceable.
Fallback if the flag proves unstable: an `InstructionProvider` that reads the same `SKILL.md` files
off disk and splices the body in. Same assets, dumber loader.

### 5.3 RF2.5 is a `ToolPredicate`, not an adapter

The PRD assigns "Injeção dinâmica de ferramentas MCP conforme o domínio da sessão" to an
`MCPServerAdapter`. In ADK this is one function:

```python
def by_domain(tool, readonly_context) -> bool:
    domain = readonly_context.state.get("session:domain")
    return tool.name in ALLOWED[domain]

McpToolset(connection_params=..., tool_filter=by_domain)
```

`_is_tool_selected` calls the predicate with the `ReadonlyContext` on every `get_tools()`
(`google/adk/tools/base_toolset.py:194-205`), and `McpToolset.get_tools()` applies it after listing
the server's tools — so the visible toolset genuinely varies per invocation. This is a **strict
improvement over Hermes**, whose `include`/`exclude` lists are static config in `config.yaml`.

Corollary for the map's open "MCP surface" question: adding a domain-scoped tool surface does not by
itself require the MCP server to become stateful. The scoping lives client-side in the ADK agent;
`pipeline`'s server can stay stateless and keep exposing its full read-only surface.

### 5.4 Learner state: use ADK session state prefixes; ignore Hermes' file-based memory

Hermes' `MEMORY.md`/`USER.md` are markdown files curated by the LLM itself. **Do not copy this.** A
`MasteryScore` is a number that a knowledge-tracing algorithm owns, not a fact an LLM should be
free-writing into a markdown file. The PRD is already right here (`LearnerStateRepositoryPort` +
SQLite).

What to take instead is the *scoping* idea, which ADK expresses better:

- `user:` — the learner model proper (durable across sessions). With the single-learner standing
  decision, `user:` and `app:` collapse, so pick one and be consistent; **drop `user_id` from the
  port signatures** in PRD §5.1 accordingly.
- (unprefixed) — this tutoring session: current `StudyPlan` node, turn count, domain.
- `temp:` — within-turn scratch (a quiz being graded), explicitly discarded after the invocation.

And take the *nudge* idea in a disciplined form: Hermes runs a background review after each turn
that may write memory. The tutor's equivalent is an `after_model_callback`/`BasePlugin` hook that
inspects the turn for assessment evidence and emits a `state_delta` — never direct `session.state`
mutation, which ADK explicitly warns bypasses event history and persistence.

### 5.5 Borrow the hook taxonomy, use ADK's callbacks

Hermes' three-way split — **control** (can block) / **transform** (can rewrite) / **observer**
(read-only) — is a genuinely useful vocabulary for the PRD's guardrails, and maps onto ADK cleanly:

| Tutor need | ADK hook |
|---|---|
| Strict grounding (RNF2): reject an answer with no vault citation | `after_model_callback` (transform) |
| Record assessment evidence → mastery delta | `after_tool_callback` / `after_model_callback` (observer + `state_delta`) |
| Block a quiz-generation tool on a concept the plan hasn't reached | `before_tool_callback` (control) |
| Splice the current `StudyPlan` frontier into the request | `before_model_callback` (control) |

Also copy Hermes' isolation rule — a failing hook logs and is skipped, it does not kill the session
— and its inverse, `fail_closed` for anything that is a *guard* rather than an enrichment. Grounding
enforcement should fail closed; telemetry should not.

### 5.6 What NOT to borrow

- **The import-time global tool registry** (§3.4). ADK composes tools per agent explicitly; a global
  registry would make the 85%-coverage-without-I/O-mocks rule harder, not easier.
- **`SOUL.md` as a single-file global identity.** Hermes explicitly loads it only from `HERMES_HOME`
  and never from CWD, precisely so identity *cannot* vary by context. The tutor needs the opposite:
  identity that varies by `DomainType`. Take the "identity is slot #1" ordering; leave the file.
- **Agent-authored skills** (`skill_manage`, self-improvement loop). Tempting, and out of scope: it
  is a write-back governance problem, and `agent/README.md` already documents that ADK's
  `require_confirmation` is experimental, incompatible with `DatabaseSessionService`, and unreliable
  for `McpToolset`-sourced tools. Revisit only if PRD v3 grows a write-back epic.
- **Hermes' 20+ messaging surfaces, terminal backends, cron, gateway.** Irrelevant to a local-first
  single-learner tutor.
- **`session_search` / FTS over chat history.** Cross-session continuity should come from the
  learner model, which is structured; searching old transcripts is a worse substitute.

---

## 6. Consequences for PRD v3

1. **Rename or footnote `HermesDomainOrchestrator`.** If it survives, it should be documented as a
   *composition root* — the thing that, given a `DomainType`, produces
   `(InstructionProvider, SkillToolset, ToolPredicate)` — not a domain service holding prompt
   strings. Note that the "Hermes" in the name refers to Nous Research's Hermes Agent as a design
   reference only.
2. **Epic 2 shrinks a lot.** RF2.1 → instruction provider. RF2.2–2.4 → three `SKILL.md` directories
   plus their tools. RF2.5 → one `ToolPredicate`. There is no `MCPToolRegistry` to build.
3. **Where does the harness live?** Hermes' answer ("platform differences live in the entry point,
   not the agent") argues against the PRD's placement of `hermes_orchestrator.py` inside
   `src/pipeline/domain/services/`. The persona/tool composition is an ADK concern and belongs in
   `agent/`, with `pipeline` keeping the domain core (learner model, SRS, plan) behind MCP. This
   overlaps the map's open "where the tutor runs" question — this note is evidence for putting the
   harness agent-side, not a decision.
4. **Drop `user_id`** from `LearnerStateRepositoryPort` / `ExecuteHermesSessionPort` per the
   single-learner standing decision; ADK's `user:` state prefix covers the scope distinction without
   an identity parameter.

---

## 7. Dead ends and honesty notes

- **No pedagogical Hermes exists.** Searches for a "Hermes" harness with persona/pedagogy/domain
  strategies returned nothing but Nous Research's Hermes Agent and the Hermes model line. If the
  PRD's author had a specific other artifact in mind, it is not publicly documented.
- **The PRD's provenance is shaky** (the "OKF da Google" misattribution). Other unexplained proper
  nouns in it — `QuizGeneratorSkill`, `QualityEvalSkill`, `SocraticDialogueEngine` — should be
  treated as invented placeholders unless someone produces a source, not as named prior art to
  match.
- **Hermes docs describe intent, not always behaviour** (issue #2817: four hooks documented and
  never invoked for ~2 weeks). Every Hermes claim in this note is cited to a doc page or the repo;
  none of it was executed or verified against a running Hermes.
- **ADK skills are experimental** and behind a feature flag; the mitigation is §5.2's fallback.
- **Not investigated**: ADK's `MemoryService` in depth, and whether `SkillToolset` composes cleanly
  with `LiteLlm`+Ollama tool-calling at the model sizes this stack uses (`llama3.1:8b`). The skills
  flow adds several tools and a fairly long system instruction; **a small local model may not
  reliably call `load_skill` before answering**. That is a real risk to §5.2 and is worth a
  `/prototype` spike before PRD v3 commits.

---

## Sources

Hermes Agent (primary):
- <https://github.com/NousResearch/hermes-agent> — repo, MIT
- <https://hermes-agent.nousresearch.com/docs/developer-guide/architecture> ([md source](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/developer-guide/architecture.md))
- <https://hermes-agent.nousresearch.com/docs/developer-guide/prompt-assembly>
- <https://hermes-agent.nousresearch.com/docs/user-guide/features/skills>
- <https://hermes-agent.nousresearch.com/docs/user-guide/features/personality>
- <https://hermes-agent.nousresearch.com/docs/user-guide/features/tools>
- <https://hermes-agent.nousresearch.com/docs/user-guide/features/memory>
- <https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp>
- <https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks>
- <https://github.com/NousResearch/hermes-agent/issues/2817>, <https://github.com/NousResearch/hermes-agent/pull/3542>

Standards:
- <https://agentskills.io/specification> — Agent Skills / `SKILL.md`

Google ADK (primary):
- <https://adk.dev/agents/llm-agents/>, <https://adk.dev/sessions/state/>, <https://adk.dev/skills/>
- Installed source, `google-adk==2.6.3`, `agent/.venv/lib/python3.12/site-packages/google/adk/`:
  `utils/instructions_utils.py`, `agents/llm_agent.py`, `tools/base_toolset.py`,
  `tools/mcp_tool/mcp_toolset.py`, `tools/skill_toolset.py`, `skills/{models,prompt,skill_registry}.py`,
  `plugins/base_plugin.py`, `features/_feature_registry.py`

Repo-local:
- `docs/projeto/PRDs/PRD AI Tutor.md` (v2), `agent/README.md`, `agent/knowledge_retrieval_agent/agent.py`

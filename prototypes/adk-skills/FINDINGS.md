# Spike: ADK SkillToolset + LiteLlm + Ollama (issue #12)

Throwaway. Not to be merged. `google-adk==2.6.3`, local Ollama.

## How to run

```bash
cd agent
uv run python ../prototypes/adk-skills/run.py                       # llama3.1:8b (default)
OLLAMA_CHAT_MODEL=qwen3.5:4b uv run python ../prototypes/adk-skills/run.py
uv run python ../prototypes/adk-skills/control.py                   # single FunctionTool control
```

Two pedagogy skills, each required to emit a marker (`[SOCRATIC]` /
`[CODE-DRILL]`), so following the skill is trivially detectable. Three
prompts: clearly humanities, clearly software, ambiguous.

## Result

**`SKILL_TOOLSET` is not experimental.** In 2.6.3 it is
`FeatureStage.STABLE, default_on=True`. No feature flag needed.

**With `llama3.1:8b` (the current default in `agent/`): total failure.** Zero
real function calls across every prompt. The model *narrates* tool calls as
prose — and hallucinates: it invented a skill named `binary_search` and then
invented its contents.

**With `qwen3.5:4b`: works, unreliably.** 2 of 3 prompts ran the full flow
(`list_skills` → `load_skill` → correct skill) and emitted the right marker.
The software prompt skipped skills entirely, deciding it didn't need one
despite the skill description naming its subject area.

## Why llama3.1:8b fails — measured, not guessed

The failure is not ADK's request construction. ADK sends a well-formed tool
declaration, and `response_format` (passed as `None`) is not the cause —
calling litellm directly with the identical payload emits a proper tool call.

The trigger is **the system prompt mentioning tools**. Sampled 6 runs per
condition, identical tool and user message:

| model | neutral persona | system prompt instructing tool use |
|---|---|---|
| `llama3.1:8b` | 5/6 emitted a real tool call | **0/6** |
| `qwen3.5:4b` | 2/6 | **6/6** |

The two models respond to the same instruction in opposite directions.
Telling `llama3.1:8b` in prose that it must call a tool reliably causes it to
describe calling the tool instead of calling it.

This is fatal for `SkillToolset` specifically, because the toolset **injects
its own long tool-describing system instruction**
(`_build_skill_system_instruction`) that cannot be removed. Neutralising the
agent's own `instruction` does not help — the run in this directory does that
and still fails on `llama3.1:8b`.

Note the single-sample A/B that first suggested this was partly luck:
`llama3.1:8b` is nondeterministic here, which is why the table above is
sampled rather than a single run.

## Other observations

- `qwen3.5:4b` leaks reasoning into the final reply ("Wait, I need to think
  about this more carefully…").
- It also called `run_skill_script({})` with no arguments, which errored.
- `list_skills_in_dir` returns `{skill_id: Frontmatter}`, not `Skill` objects;
  `SkillToolset(skills=...)` needs `load_skill_from_dir` per directory.

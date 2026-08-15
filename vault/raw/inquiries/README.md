# Inquiries

**Questions about the knowledge — not knowledge, and not ordinary captured
material.** Written here by `tutor` when teaching surfaces something about the
vault itself:

- **Coverage gap** — "the vault uses *ease factor* throughout but never defines
  it."
- **Contradiction** — "`cold-brew-coffee` says 12–24h, `cold-brew-concentrate-ratio`
  says 8h."

Both are semantic (they read the same to anyone, and say nothing about the
learner), so they may leave `tutor` — see the memory boundary in `CONTEXT.md`.

## Why a separate folder

The rest of `vault/raw/` is **material to distil**: drop a PDF or a note, and
ingest turns its *content* into concepts. An inquiry is not material. Its
useful answer is a *new concept researched from sources* (for a gap) or a
*reconciliation of two existing ones* (for a contradiction) — a verb `pipeline`
does not have yet, tracked as
[issue #15](https://github.com/Wedeueis/ai-tutor/issues/15).

Until that flow exists, anything here would be ingested like any other note,
producing a concept *about the gap* rather than one that fills it. Keeping
inquiries in their own folder means:

1. They are visibly distinguishable from material you captured deliberately.
2. The research-and-synthesise flow has a defined place to read from when it
   lands, instead of having to guess which inbox files are questions.
3. You can exclude them from ingest with one path rule rather than by
   inspecting content.

## Not part of the OKF bundle

`vault/raw/` is a capture surface, not knowledge (`CLAUDE.md`). Files here
carry no frontmatter and are never linked from finished concepts. Nothing in
this folder is a concept, and `tutor` never writes the bundle itself — see
[issue #8](https://github.com/Wedeueis/ai-tutor/issues/8).

Proposed *new concepts* are a different case and do not belong here: they wait
in `tutor/proposals/` for human approval, and are approved by moving them into
`vault/raw/`.

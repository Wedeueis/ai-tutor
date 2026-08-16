# Proposals

**Derived concepts `tutor` produced while teaching, waiting for a person.**

A synthesis that comes out of a session — two concepts turning out to describe
the same effect, a worked distinction neither of them states — is knowledge: it
reads the same to anyone, and it passes the boundary test in `CONTEXT.md`. So
it may leave `tutor`. What it may *not* do is walk into the vault on its own.

## Approving one is `mv`

```bash
mv tutor/proposals/2026-08-16-tutor-concept-<slug>.md vault/raw/
```

That is the whole approval step, and it is deliberately a human's hand.
`pipeline` remains the only thing that ever creates a concept
([#8](https://github.com/Wedeueis/ai-tutor/issues/8)); once the file is in
`vault/raw/`, ingest treats it like any other captured note — distilling it,
scoring it against the quality rubrics, and deciding for itself whether it
becomes a concept.

Rejecting one is `rm`. Nothing tracks the decision, because a proposal nobody
wanted is not a fact worth keeping.

## Why not the inbox directly

`vault/raw/inquiries/` gets **questions** about the vault (coverage gaps,
contradictions) automatically, because a question creates no knowledge — it
asks for some. A proposal is an answer, and an answer that arrived without
anyone looking at it is exactly what the memory boundary exists to prevent.

These files carry no frontmatter, for the same reason nothing else in
`vault/raw/` does: they are raw material, not concepts. That is also what makes
approval a plain `mv` rather than a conversion.

Files here are tracked in git on purpose — the point is that a person sees
them.

# Context

The ubiquitous language for this repo. Glossary only — no implementation
detail, no specs, no decisions. Decisions live in the issue tracker; how
things are built lives in each component's own docs.

## Memory

**Semantic memory** — knowledge that stands on its own: definitions,
relationships, syntheses, contradictions between them. It reads the same to
anyone, whether or not they were present when it was written. Semantic memory
lives in the **vault**.

**Episodic memory** — the record of a particular learner's particular
sessions: what was covered, what was answered wrongly, what they repeatedly
confuse, when a card is next due. It is meaningless to anyone but that
learner. Episodic memory lives in **`tutor`**, never in the vault.

The dividing test: *would this make sense to someone who never took the
session?* Yes means semantic; no means episodic. The two never mix — a note
about the knowledge may reach the vault, a note about the learner may not,
and no exception has been carved for either direction.

## Knowledge

**Concept** — one markdown document in the vault; one unit of knowledge. Its
id is its file path minus `.md`. See `WIKI_SPEC.md` for the normative
definition.

**Domain** — the coarsest classification of a concept (`type: Domain`, e.g.
Machine Learning, Coffee). A concept has at most one, and often none:
withholding is the classifier's honest answer, not a failure.

**Category** — a finer classification beneath a Domain (`type: Category`). A
concept has many. Machine-derived, used as a retrieval signal.

**Prerequisite** — a typed relation asserting that understanding one concept
requires understanding another (`requires:: [[/target]]`, written on the
dependent concept). A property of the knowledge, not of any learner.

**Inbox** — `vault/raw/`. Captured material awaiting distillation. Explicitly
*not* part of the knowledge bundle: things in it are candidates, not
knowledge.

**Quality** — whether a draft is well-formed knowledge judged on its own:
traceable to its source, substantial, accurately titled. Intrinsic; needs
nothing but the draft.

**Relevance** — whether a draft belongs in *this* bundle: not already
covered, and on-topic for what the bundle is about. Extrinsic; cannot be
judged without the rest of the vault. Distinct from quality — a well-written
note about something irrelevant is high quality and low relevance.

**Credibility signal** — an objective fact about a source (`author`,
`last_modified`, `usage_count`) from which a consumer may *infer* how much to
trust what was extracted from it. The signals are recorded; a credibility
score never is. Absent signals mean *unknown*, which is neutral, not low.

## Learning

**Learner** — the person being taught. This system has exactly one.

**Mastery** — how well the learner knows one concept. Episodic.

**Pedagogy** — a way of teaching, bound to a Domain. Owned by `tutor`; the
vault never describes how to teach anything. A pedagogy shapes *how* the
tutor teaches and may narrow which tools it uses; it can never widen them,
and it can never weaken the invariants.

**Invariant** — a constraint that holds no matter which pedagogy is in play:
ground strictly in the vault, never write the bundle directly, never let
episodic content cross into it. Invariants are composed last, after any
pedagogy, so nothing downstream can override them.

**Depth target** — how far the learner intends to go in one Category: a named
level (*aware*, *working*, *specialist*), each defining a durability
threshold and what evidence counts toward it. Learner intent, so episodic —
the vault never records what someone wants to specialise in. Untargeted
Categories default to *aware*.

**Usage** — how often the learner has read, been taught, or been tested on a
concept. Episodic: it is a fact about the learner, so it is counted in
`tutor` and never written to the vault. Not to be confused with a source's
`usage_count`, which is a property of external material.

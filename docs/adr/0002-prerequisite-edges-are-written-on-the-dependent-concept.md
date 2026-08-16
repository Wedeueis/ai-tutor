# Prerequisite edges are written on the dependent concept

A `requires::` edge lives in the body of the concept that **depends**, and
points at the concept that must be understood **first**:

```markdown
<!-- in /multi-head-attention.md -->
requires:: [[/scaled-dot-product-attention]]
```

Read aloud: *"multi-head attention requires scaled dot-product attention."* The
source of the edge is the dependent; the target is the prerequisite. Every
consumer — `select_prerequisites`, the judgement prompt, `trace_lineage`, the
gold set, and `tutor`'s study-plan projection — uses that same direction.

This is the direction Dataview inline fields already imply (`key:: value` is a
statement *about the note it appears in*), and it is what makes the study plan
a simple outgoing walk: from what the learner wants to study, to what they need
first.

## Why this is worth an ADR

The convention is one word wide and reverses cleanly, so a reader can hold the
opposite of it without noticing. It cost us a full measurement cycle.

The 30-pair gold set for the prerequisite gate (RF1.3) was labelled with
`source` and `target` transposed — as *"target requires source"*. Nothing about
that is unreasonable in isolation; both directions read fine in a JSON file
with two string fields. But the measured consequences were severe and
misleading:

| gold set direction | model | precision |
|---|---|---|
| transposed | `llama3.1:8b` | 0.517 |
| transposed | `claude-sonnet-4.5` | **0.000** |
| corrected | `claude-sonnet-4.5` | **1.000** |

The first number looked like a *tuning* problem and sent us to weigh rubrics
and sweep thresholds. The second looked like a catastrophic model failure. Only
the third revealed that the rubrics, the thresholds, and the flat-mean rollup
had been correct throughout.

The 0.517 was the most expensive result, because a weak model that says yes to
almost everything scores near chance whatever the labels do — it looked like
partial signal, and partial signal invites tuning. A model that actually judges
direction produced the near-zero that made the inversion visible.

## Consequences

- **Any labelled data, fixture, or test for prerequisites states the dependent
  first.** `{"source": "multi-head-attention", "target": "scaled-dot-product-attention",
  "is_prerequisite": true}` means multi-head attention requires the other.
- **A gold set must contain reversed pairs as hard negatives**, and ours does:
  for several concepts both directions appear, one true and one false. That is
  what makes a transposition detectable at all — a set of true pairs alone
  scores identically under either reading.
- **A precision result near zero from a capable model should be read as a
  possible convention mismatch before it is read as a model failure.** A model
  that is wrong about everything, consistently, is usually answering a
  different question than the one being scored.
- The reciprocal edge is deliberately never written. "A requires B" is a claim
  about A; asserting the reverse would state a dependency nobody judged.

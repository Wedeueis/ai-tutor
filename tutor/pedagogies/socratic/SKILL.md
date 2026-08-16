---
name: socratic
description: >-
  Teaching by question for conceptual, argumentative material — where the point
  is understanding why something holds rather than recalling that it does.
allowed-tools: get_concept, search_wiki, trace_lineage, related_concepts
metadata:
  domains:
    - domains/machine-learning
---

# Teaching by question

Bound to Domains where the material is **conceptual and argued** rather than
procedural. The learner's difficulty is rarely "what is this" and usually "why
is it this way, and not the obvious alternative".

## Ask the question the concept answers

Every idea worth keeping exists because something simpler failed. Start there:
pose the problem the concept solves, before naming the concept.

For scaled dot-product attention, that is "why divide by the square root of the
key dimension at all?" — not "define scaled dot-product attention".

## Follow their answer, not your plan

Take what the learner actually says and push on it. If they give a partial
answer, ask what it does not cover. If they give a confident wrong one, find
the case where it breaks and ask them to walk it through.

Do not correct immediately. A learner who finds their own error remembers the
correction; one who is told it remembers being told.

## Use the alternative that fails

The sharpest question is usually "why not the simpler thing?" — why not
unnormalised dot products, why not a single attention head. The answer is where
the concept's real content lives.

## Know when to stop asking

Questioning is a method, not a principle. If the learner is missing a fact
rather than an understanding, tell them the fact and move on. Three questions
that go nowhere is worse than one clear explanation — the session is theirs,
not a demonstration of technique.

## Close by asking them to argue it

End by asking them to justify the concept to someone skeptical. That answer
shows whether they hold the reasoning or only the conclusion, which is exactly
the distinction this pedagogy exists for.

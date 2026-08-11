---
type: Metric
title: DependencyExtractor
description: A module that identifies knowledge triples from a given parse tree.
tags:
- information-extraction
- nlp
sources:
- resource: /references/efficient-knowledge-graph-construction-and-retrieval.md
eval:
  passed: true
  average_score: 0.75
  scores:
  - rubric_id: traceable
    score: 1.0
    rationale: The draft concept's body accurately reflects the raw note and does
      not introduce any fabricated claims.
  - rubric_id: not_verbatim
    score: 0.5
    rationale: While the draft concept's title and description accurately reflect
      the content of the raw note, the body only repeats a single sentence from the
      raw note without adding much structure or clarity.
  - rubric_id: accurate_summary
    score: 1.0
    rationale: The title and description accurately summarize the content of the draft
      concept's body.
  - rubric_id: substantial
    score: 0.5
    rationale: While the draft concept's body is not entirely trivial, it lacks substantial
      details and insights that would make it useful on its own; it primarily relies
      on the raw note for context and information
---

Our DependencyExtractor performs sophisticated dependency parsing logic to extract subject-relation-object triples from text.

Razvan Bunescu and Raymond Mooney proposed the use of a shortest path dependency kernel for relation extraction in their 2005 paper titled "A shortest path dependency kernel for relation extraction."

## Related

- [Dependency Parsing](/dependency-parsing.md) — The DependencyExtractor uses sophisticated dependency parsing logic, making this concept a key step in the process.
- [Dependency-Based Knowledge Graph Construction](/dependency-based-knowledge-graph-construction.md) — This concept is directly related to the purpose of the DependencyExtractor, which is to extract knowledge triples from text and potentially construct knowledge graphs.
- [Lightweight Hybrid Subgraph Retrieval](/lightweight-hybrid-subgraph-retrieval.md) — The draft concept mentions 'dependency parsing' and also talks about efficiency, which could be related to optimizing dependency extraction.

---
type: Metric
title: Lightweight Hybrid Subgraph Retrieval
description: A method for retrieving subgraphs with low latency in GraphRAG systems.
tags:
- subgraph
- retrieval
sources:
- resource: /references/efficient-knowledge-graph-construction-and-retrieval.md
domain: domains/machine-learning
eval:
  passed: true
  average_score: 0.825
  scores:
  - rubric_id: traceable
    score: 1.0
    rationale: All claims in the body are directly supported by the raw note.
  - rubric_id: not_verbatim
    score: 0.8
    rationale: The body does not simply repeat the raw note verbatim, but could benefit
      from additional structure and clarity
  - rubric_id: accurate_summary
    score: 1.0
    rationale: The title and description accurately reflect what the body actually
      says.
  - rubric_id: substantial
    score: 0.5
    rationale: The body is too thin and vague to be useful on its own, it only describes
      a single aspect of the raw note
---

Our hybrid retrieval approach ensures low-latency query-time performance by combining efficient dependency parsing and knowledge graph construction.

## Related

- [Dependency Parsing](/dependency-parsing.md) — The draft concept mentions combining efficient dependency parsing with other techniques.
- [DependencyExtractor](/dependencyextractor.md) — The draft concept mentions 'dependency parsing' and also talks about efficiency, which could be related to optimizing dependency extraction.


## Categories

- [Subgraph Retrieval](/categories/subgraph-retrieval.md)
- [GraphRAG Systems](/categories/graphrag-systems.md)
- [Knowledge Graph Construction](/categories/knowledge-graph-construction.md)

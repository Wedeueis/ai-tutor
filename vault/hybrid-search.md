---
type: Metric
title: Hybrid Search
description: A search technique that combines multiple retrieval methods to improve
  results.
tags:
- information retrieval
- search engines
sources:
- resource: /references/efficient-knowledge-graph-construction-and-retrieval.md
eval:
  passed: true
  average_score: 0.725
  scores:
  - rubric_id: traceable
    score: 0.6
    rationale: The draft concept mentions 'information retrieval systems', which aligns
      with the raw note's CCS Concepts, but does not directly reference or build upon
      any specific fact from the note.
  - rubric_id: not_verbatim
    score: 1.0
    rationale: The body provides a clear and concise rephrasing of what hybrid search
      entails, adding structure to the concept.
  - rubric_id: accurate_summary
    score: 0.5
    rationale: The title 'Hybrid Search' is accurate, but the description could be
      more specific about combining multiple retrieval methods.
  - rubric_id: substantial
    score: 0.8
    rationale: The body provides enough detail to understand what hybrid search is,
      but lacks concrete examples or a deeper analysis of its strengths and potential
      applications.
---

Hybrid search is a technique used in information retrieval systems to combine the strengths of different retrieval methods. It can be used to improve the accuracy and relevance of search results.

The HybridChunker chunks input documents using a two-stage approach. First, it splits documents at Markdown headers to preserve semantic cohesion. Then, it applies character-level splitting when sections exceed predefined size limits. The chunking configuration uses a maximum size of 2048 characters with 200-character overlap.

**Reciprocal Rank Fusion**

A technique for combining the results of semantic search and graph search. It produces a best result by taking into account both methods.

## Related

- [Beam search](/beam-search.md) — Hybrid search and beam search both optimize search results by leveraging different methods, but the former combines multiple retrieval methods in general.
- [Hyperparameter Tuning](/hyperparameter-tuning.md) — Both hybrid search and hyperparameter tuning involve selecting or combining optimization strategies to improve performance, with the latter applying to machine learning models and the former to information retrieval systems.

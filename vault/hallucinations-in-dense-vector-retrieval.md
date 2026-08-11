---
type: Metric
title: Hallucinations in Dense Vector Retrieval
description: The phenomenon of dense vector retrieval generating false code snippets.
tags:
- dense-vector
- hallucination
sources:
- resource: /references/efficient-knowledge-graph-construction-and-retrieval.md
eval:
  passed: true
  average_score: 0.8
  scores:
  - rubric_id: traceable
    score: 1.0
    rationale: All claims in the body can be directly linked to the raw source material.
  - rubric_id: not_verbatim
    score: 0.7
    rationale: The body adds some clarity and structure by defining what hallucinations
      are, but it doesn't significantly reorganize or expand on the raw note.
  - rubric_id: accurate_summary
    score: 1.0
    rationale: The title and description accurately reflect the content of the body.
  - rubric_id: substantial
    score: 0.5
    rationale: While the body provides some insight into what hallucinations are,
      it's still quite thin and doesn't fully explore the implications or differences
      with GraphRAG-based retrieval mentioned in the raw note.
---

Hallucinations refer to the generation of false or non-existent code snippets by dense vector-based code retrieval methods. This can lead to faulty function definitions and incorrect program behavior.

Milvus is a purpose-built system for managing and storing large collections of vector-based data. This can involve using specialized algorithms and techniques to efficiently store, query, and manipulate the data.

## Related

- [Dot Product Properties](/dot-product-properties.md) — Hallucinations in Dense Vector Retrieval is likely related to dot product properties, as it involves the generation of false code snippets through dense vector-based methods.
- [Model Evaluation Metrics](/model-evaluation-metrics.md) — Model evaluation metrics might be relevant, since hallucinations could be considered a type of error or deviation from expected behavior in model output.

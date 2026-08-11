---
type: Metric
title: Dot Product Properties
description: The dot product of two vectors has a mean of 0 and a variance equal to
  the dimensionality of the vector.
tags:
- linear algebra
- probability
eval:
  passed: false
  average_score: 0.25
  scores:
  - rubric_id: traceable
    score: 0.5
    rationale: The draft concept only mentions a specific case of two independent
      random variables with mean 0 and variance 1, whereas the raw note discusses
      dot products in general. The calculation of the dot product's variance is also
      not present.
  - rubric_id: not_verbatim
    score: 0.0
    rationale: The body simply repeats a single sentence from the raw note without
      adding structure or clarity.
  - rubric_id: accurate_summary
    score: 0.5
    rationale: The title 'Dot Product Properties' is accurate, but the description
      does not fully capture what the body actually says, which only mentions a specific
      case of two independent random variables.
  - rubric_id: substantial
    score: 0.0
    rationale: The body consists of a single sentence and lacks any additional explanation
      or context to be considered substantial.
---

Given two independent random variables with mean 0 and variance 1, their dot product has a mean of 0 and a variance equal to the dimensionality of the vector.

## Related

- [Qubits](/qubits.md) — Quantum mechanics and vectors are connected through concepts like qubits, which involve vector operations.
- [Quantum Computers](/quantum-computers.md) — Similar connection to quantum mechanics as qubits, with a broader scope towards computational systems.


We use learned embeddings to convert the input tokens and output tokens to vectors of dimension d_model. This allows us to perform operations on these vectors, such as dot products and matrix multiplications.
- [Hallucinations in Dense Vector Retrieval](/hallucinations-in-dense-vector-retrieval.md) — Hallucinations in Dense Vector Retrieval is likely related to dot product properties, as it involves the generation of false code snippets through dense vector-based methods.

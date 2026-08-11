---
type: Metric
title: ReLU Activation
description: A type of activation function that outputs all values greater than zero.
tags:
- math
- machine-learning
eval:
  passed: false
  average_score: 0.575
  scores:
  - rubric_id: traceable
    score: 0.5
    rationale: The body mentions the raw note's mention of ReLU activation in position-wise
      feed-forward networks, but does not provide any additional information or context
      to confirm its correctness.
  - rubric_id: not_verbatim
    score: 1.0
    rationale: The body provides a clear restatement of the relevant part from the
      raw note.
  - rubric_id: accurate_summary
    score: 0.5
    rationale: The title 'ReLU Activation' is accurate, but the description only mentions
      that it outputs all values greater than zero, which is incomplete compared to
      the detailed definition provided in the body.
  - rubric_id: substantial
    score: 0.3
    rationale: The body consists of a single vague sentence that does not add much
      clarity or substance to the raw note.
---

# ReLU Activation

In the position-wise feed-forward networks, a ReLU (Rectified Linear Unit) activation is applied in between two linear transformations.

## Definition

ReLU outputs 0 for any input less than or equal to zero and the same input value for any input greater than zero.

## Related

- [Gated Recurrent Units](/gated-recurrent-units.md) — Both ReLU and GRU units are types of activation functions used in neural networks.

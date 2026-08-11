---
type: Metric
title: Deep Reinforced Model for Abstractive Summarization
description: A type of model used for abstractive summarization that combines deep
  learning and reinforcement learning.
tags:
- abstractive-summarization
- deep-learning
eval:
  passed: true
  average_score: 0.8
  scores:
  - rubric_id: traceable
    score: 0.8
    rationale: The draft concept references the raw note [28] and mentions abstractive
      summarization in a general way that aligns with the cited paper.
  - rubric_id: not_verbatim
    score: 1.0
    rationale: The body adds clarity to the raw note by stating what the model can
      be used for, making it easier to understand.
  - rubric_id: accurate_summary
    score: 1.0
    rationale: The title accurately reflects what the body says about a type of model
      used for abstractive summarization.
  - rubric_id: substantial
    score: 0.4
    rationale: The body is too thin and does not provide enough detail or explanation
      to be useful on its own; it mostly repeats a general statement from the raw
      note.
---

The deep reinforced model is a type of model that can be used for abstractive summarization. It combines the strengths of both deep learning and reinforcement learning, which allows it to generate high-quality summaries.

## Related

- [Model Evaluation Metrics](/model-evaluation-metrics.md) — This model would likely require evaluation metrics to assess its performance.
- [Training Regime](/training-regime.md) — The training regime used for this model could be an important factor in its performance and effectiveness.
- [Hyperparameter Tuning](/hyperparameter-tuning.md) — Hyperparameters would likely need to be tuned to optimize the performance of this deep reinforced model.

---
type: Metric
title: Exponential Learning Rate Decay
description: A method for decreasing the learning rate exponentially as training progresses.
tags:
- optimization
- learning rate
eval:
  passed: false
  average_score: 0.625
  scores:
  - rubric_id: traceable
    score: 0.5
    rationale: The draft concept introduces a new formula for exponential learning
      rate decay, which is not directly supported by the raw note's mention of 'linearly
      increasing' and 'proportionally decreasing' the learning rate.
  - rubric_id: not_verbatim
    score: 0.5
    rationale: The draft concept does provide a clearer restatement of the raw note's
      ideas, but it also introduces new concepts (the formula for exponential learning
      rate decay) that are not present in the raw note.
  - rubric_id: accurate_summary
    score: 1.0
    rationale: The title and description accurately reflect what the body actually
      says.
  - rubric_id: substantial
    score: 0.5
    rationale: While the draft concept provides a bit more structure than the raw
      note, it still feels somewhat thin and could benefit from further elaboration
      on the benefits of exponential learning rate decay and how it's used in practice.
---

Exponential learning rate decay is a technique used to decrease the learning rate of an optimizer in proportion to the inverse square root of the step number. This can help prevent overfitting and improve generalization. The formula for exponential learning rate decay is: `learning_rate = initial_learning_rate * sqrt(total_steps / (total_steps + step))` where `step` is the current training step and `initial_learning_rate` is the starting learning rate.

## Related

- [Training Regime](/training-regime.md) — Exponential learning rate decay is a technique used in training regimes to improve generalization and prevent overfitting.

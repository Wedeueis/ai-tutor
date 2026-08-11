---
type: Metric
title: Label Smoothing
description: A technique for improving model accuracy by introducing uncertainty during
  training.
tags:
- label smoothing
- uncertainty
- model accuracy
eval:
  passed: false
  average_score: 0.625
  scores:
  - rubric_id: traceable
    score: 1.0
    rationale: All claims in the body can be traced back to the raw source material.
  - rubric_id: not_verbatim
    score: 0.5
    rationale: The body simply repeats a sentence from the raw note without adding
      structure or clarity.
  - rubric_id: accurate_summary
    score: 0.8
    rationale: While the title and description are mostly accurate, they don't fully
      capture the nuances of the technique described in the body.
  - rubric_id: substantial
    score: 0.2
    rationale: The body is a single sentence that doesn't provide enough information
      to be useful on its own; it's too thin and lacks context.
---

During training, we employed label smoothing of value ϵ ls = 0 . 1 [36]. This hurts perplexity, as the model learns to be more unsure, but improves accuracy and BLEU score.

## Related

- [Training Regime](/training-regime.md) — Label smoothing is a technique used in model training.
- [Exponential Learning Rate Decay](/exponential-learning-rate-decay.md) — Both involve modifying the learning process during training.

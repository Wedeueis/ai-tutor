---
type: Reference
title: WMT Dataset
description: A large-scale dataset for machine translation, containing millions of
  sentence pairs.
tags:
- machine translation
- natural language processing
eval:
  passed: true
  average_score: 0.75
  scores:
  - rubric_id: traceable
    score: 1.0
    rationale: All claims in the body are directly supported by the raw note, with
      specific numbers and attributions.
  - rubric_id: not_verbatim
    score: 0.5
    rationale: The body adds some clarity but still largely repeats the raw note verbatim;
      a more structured restatement would be an improvement.
  - rubric_id: accurate_summary
    score: 1.0
    rationale: The title and description accurately reflect what the body says, with
      no discrepancies or omissions.
  - rubric_id: substantial
    score: 0.5
    rationale: While the body provides some useful information, it is still a bit
      thin and lacks detail; more context would be needed to make it truly substantial.
---

The WMT (Wikipedia-based Machine Translation) dataset is a collection of sentence pairs used to train and evaluate machine translation models. It contains millions of sentences, with the English-German dataset consisting of approximately 4.5 million pairs and the English-French dataset containing over 36 million pairs.

## Related

- [Training Regime](/training-regime.md) — The WMT dataset is used to train machine translation models, which involves a specific training regime.
- [Position-wise Feed-Forward Networks](/position-wise-feed-forward-networks.md) — Machine translation models often utilize position-wise feed-forward networks as a key component.
- [Dependency-Based Knowledge Graph Construction](/dependency-based-knowledge-graph-construction.md) — The draft concept mentions using industrial-grade NLP libraries, which could be related to specific datasets used for training these libraries.

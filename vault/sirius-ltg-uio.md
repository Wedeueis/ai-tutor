---
type: Metric
title: Sirius-LTG-UIO
description: A model for extracting semantic relations from scientific papers.
tags:
- relations
- extraction
sources:
- resource: /references/efficient-knowledge-graph-construction-and-retrieval.md
eval:
  passed: true
  average_score: 0.8
  scores:
  - rubric_id: traceable
    score: 1.0
    rationale: 'The draft concept accurately references the source material ''Sirius-ltg-uio
      at semeval-2018 task 7: Convolutional neural networks with shortest dependency
      paths for semantic relation extraction and classification in scientific papers''.'
  - rubric_id: not_verbatim
    score: 0.5
    rationale: The draft concept does not provide a clear restatement or summary of
      the source material; it seems to be merely paraphrasing the title.
  - rubric_id: accurate_summary
    score: 0.8
    rationale: The title and description capture the essence of the body's content
      but could be more precise in describing what the model actually does.
  - rubric_id: substantial
    score: 0.9
    rationale: The draft concept provides some insight into how the model works, albeit
      briefly; it lacks concrete details or real-world applications.
---

Sirius-LTG-UIO is a model that uses convolutional neural networks to extract and classify semantic relations within scientific papers. This can involve identifying relationships between entities, concepts, or other relevant components of the text.

## Related

- [Long Short-Term Memory (LSTM)](/long-short-term-memory-lstm.md) — Both concepts involve the use of neural networks for tasks in natural language processing.
- [Gated Recurrent Units](/gated-recurrent-units.md) — Like Sirius-LTG-UIO, Gated Recurrent Units also utilize a type of recurrent neural network architecture

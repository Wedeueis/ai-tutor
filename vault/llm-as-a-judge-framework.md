---
type: Metric
title: LLM-as-a-Judge Framework
description: A framework that utilizes a large language model to evaluate generated
  migration code against ground truth.
tags:
- ai
- evaluation
- migration
sources:
- resource: /references/efficient-knowledge-graph-construction-and-retrieval.md
eval:
  passed: true
  average_score: 0.75
  scores:
  - rubric_id: traceable
    score: 1.0
    rationale: All claims in the body can be directly linked to the raw note, with
      no fabricated facts or numbers.
  - rubric_id: not_verbatim
    score: 0.7
    rationale: The body adds a general description of the framework, but it does not
      provide additional structure or clarity beyond what is in the raw note.
  - rubric_id: accurate_summary
    score: 1.0
    rationale: The title and description accurately reflect what the body says, with
      no discrepancies or inaccuracies.
  - rubric_id: substantial
    score: 0.3
    rationale: The body contains a single vague sentence that does not provide much
      insight on its own. It lacks substantial content to be useful.
---

The LLM-as-a-Judge framework is a novel approach to evaluating generated migration code. It leverages the power of large language models to compare generated outputs with reference migrated versions, providing an accurate and unbiased assessment of code quality.

## Related

- [Model Evaluation Metrics](/model-evaluation-metrics.md) — The framework uses large language models to evaluate generated migration code, which is a form of model evaluation.
- [BLEU Score](/bleu-score.md) — The framework compares generated outputs with reference migrated versions, which is similar to the concept of evaluating machine-generated text against human-written text using metrics like BLEU score.
- [RAG Does Not Work for Enterprises](/rag-does-not-work-for-enterprises.md) — Both concepts involve evaluating or judging the effectiveness of a particular approach (RAG) in certain contexts.

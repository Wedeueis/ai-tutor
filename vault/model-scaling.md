---
type: Metric
title: Model Scaling
description: Evaluating the impact of increasing computational resources on model
  performance.
tags:
- scaling
- computational resources
sources:
- resource: /references/efficient-knowledge-graph-construction-and-retrieval.md
eval:
  passed: true
  average_score: 0.7
  scores:
  - rubric_id: traceable
    score: 0.8
    rationale: The draft concept mentions TFLOPS values for different hardware, which
      is traceable to the raw note. However, it does not specify that these values
      were measured on the development set, newstest2013.
  - rubric_id: not_verbatim
    score: 0.6
    rationale: The body of the draft concept is similar to a sentence from the raw
      note, but it lacks structure and clarity. It could benefit from headings or
      lists to summarize the results.
  - rubric_id: accurate_summary
    score: 1.0
    rationale: The title 'Model Scaling' accurately reflects what the body says about
      evaluating the impact of increasing computational resources on model performance.
  - rubric_id: substantial
    score: 0.4
    rationale: The body is too thin and lacks specific results or metrics to be useful
      on its own. It only mentions testing different TFLOPS values without providing
      any concrete outcomes.
---

We explored how scaling up our model's computing power, measured in TFLOPS (tera-floating-point operations per second), influenced its performance. Specifically, we tested values of 2.8, 3.7, 6.0, and 9.5 TFLOPS for K80, K40, M40, and P100 hardware.

The cost evaluation of GPT-4-based KG construction reveals that the process can be computationally expensive, particularly when performed in serial. However, parallelization can significantly reduce the computational time required for this task.

## Related

- [Training Regime](/training-regime.md) — Model scaling often involves adjusting the training regime to take advantage of increased computational resources.
- [Exponential Learning Rate Decay](/exponential-learning-rate-decay.md) — Changes in model scaling can influence learning rate decay, making this concept relevant for further exploration.


Bigger models are generally better, indicating that increased capacity can lead to improved results. However, this also increases the risk of over-fitting, which dropout can help mitigate.

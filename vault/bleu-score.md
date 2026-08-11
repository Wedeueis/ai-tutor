---
type: Metric
title: BLEU Score
description: A metric used to evaluate the quality of machine translations.
tags:
- machine translation
- evaluation metrics
eval:
  passed: false
  average_score: 0.65
  scores:
  - rubric_id: traceable
    score: 0.5
    rationale: The draft concept mentions BLEU score as a metric for evaluating machine
      translation quality, but it does not specify that the note is from WMT 2014
      or mention any results like in the raw note.
  - rubric_id: not_verbatim
    score: 0.8
    rationale: The draft concept rephrases the raw note's information about BLEU score
      and machine translation quality, but it does not add much structure beyond a
      simple definition.
  - rubric_id: accurate_summary
    score: 1.0
    rationale: The title 'BLEU Score' accurately reflects what the body says, which
      is that the metric measures machine translation quality.
  - rubric_id: substantial
    score: 0.3
    rationale: The draft concept's body is too thin and does not provide enough information
      to be useful on its own; it essentially just restates what BLEU score is.
---

# BLEU Score
The BLEU (Bilingual Evaluation Understudy) score is a widely used metric for evaluating the quality of machine translations. It measures how well a machine-generated text aligns with human-written text, taking into account the presence of common phrases and sentence structures.

A higher BLEU score indicates that the machine-generated translation is more fluent and accurate. In contrast, a lower BLEU score suggests that the translation contains errors or does not accurately capture the original meaning.

## Related

- [WMT Dataset](/wmt-dataset.md) — BLEU Score is used in machine translation evaluation, which is a key application of the WMT Dataset.
- [LLM-as-a-Judge Framework](/llm-as-a-judge-framework.md) — The framework compares generated outputs with reference migrated versions, which is similar to the concept of evaluating machine-generated text against human-written text using metrics like BLEU score.

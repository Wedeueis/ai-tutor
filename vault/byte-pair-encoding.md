---
type: Metric
title: Byte-Pair Encoding
description: A method for compressing text data into a shared vocabulary.
tags:
- natural language processing
- text compression
eval:
  passed: false
  average_score: 0.5
  scores:
  - rubric_id: traceable
    score: 0.8
    rationale: The draft concept correctly mentions byte-pair encoding and its shared
      vocabulary, but does not specifically attribute the technique to 'compressing
      text data' which is a slight simplification of the raw note's more technical
      description.
  - rubric_id: not_verbatim
    score: 0.4
    rationale: The body mostly repeats the raw note verbatim without adding significant
      structure or clarity; it would be better to break down the information into
      separate points or rephrase for emphasis.
  - rubric_id: accurate_summary
    score: 0.6
    rationale: The title is accurate but somewhat misleading as it focuses on a specific
      method (byte-pair encoding) rather than the broader concept of compressing text
      data, which is hinted at in the description.
  - rubric_id: substantial
    score: 0.2
    rationale: The body is too thin and does not provide substantial information;
      it barely scratches the surface of what was described in the raw note and lacks
      detail or further explanation.
---

Byte-pair encoding is a technique used to compress text data by grouping common pairs of characters together. This results in a more compact representation of the text, often referred to as a 'shared source-target vocabulary.' In this context, we used byte-pair encoding with a shared vocabulary of about 37,000 tokens.

## Related

- [Position-wise Feed-Forward Networks](/position-wise-feed-forward-networks.md) — Both concepts involve efficient data compression and representation techniques.

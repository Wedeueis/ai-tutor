---
type: Metric
title: Local Attention Mechanisms
description: A restricted attention mechanism for efficiently handling large inputs
  and outputs.
tags:
- machine learning
- nlp
eval:
  passed: false
  average_score: 0.55
  scores:
  - rubric_id: traceable
    score: 1.0
    rationale: The draft concept's body is entirely based on claims made in the raw
      note, with no fabricated facts or attributions.
  - rubric_id: not_verbatim
    score: 0.4
    rationale: While the draft concept does rephrase some of the raw note's content,
      it still largely repeats verbatim phrases and ideas without adding significant
      structure or clarity (e.g., 'making generation less sequential' is a direct
      quote from the raw note)
  - rubric_id: accurate_summary
    score: 0.6
    rationale: The title 'Local Attention Mechanisms' partially captures one of the
      research goals mentioned in the raw note, but the description does not accurately
      reflect what the body says, as it focuses on the idea of making generation less
      sequential rather than local attention mechanisms specifically
  - rubric_id: substantial
    score: 0.2
    rationale: The draft concept's body is a very thin and vague rephrasing of one
      sentence from the raw note, lacking any substantial content or ideas to be useful
      on its own
---

Local attention mechanisms are a type of restricted attention that is designed to handle large inputs and outputs. This approach aims to make generation less sequential, making it more efficient and scalable for various applications.

## Related

- [Attention Is All You Need](/attention-is-all-you-need.md) — Both concepts deal with attention mechanisms in neural networks.
- [Position-wise Feed-Forward Networks](/position-wise-feed-forward-networks.md) — Local attention mechanisms aim to make generation less sequential, which is also a goal of position-wise feed-forward networks.


The decomposable attention model is a type of attention mechanism that can be used in neural networks. It allows the network to focus on specific parts of the input data, which can be particularly useful when working with long-range dependencies or complex patterns.
- [Self-Attention](/self-attention.md) — Self-Attention is a type of attention mechanism, and Local Attention Mechanisms is another example of such mechanisms.

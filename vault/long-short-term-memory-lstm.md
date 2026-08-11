---
type: Metric
title: Long Short-Term Memory (LSTM)
description: A type of recurrent neural network that can learn long-term dependencies.
tags:
- machine learning
- deep learning
eval:
  passed: true
  average_score: 0.725
  scores:
  - rubric_id: traceable
    score: 0.5
    rationale: While the draft concept mentions a specific paper by Sepp Hochreiter
      and Jürgen Schmidhuber, it does not provide any direct connections to the raw
      note's references.
  - rubric_id: not_verbatim
    score: 1.0
    rationale: The body of the draft concept provides a clear and concise summary
      of what an LSTM is, without simply repeating the raw note verbatim.
  - rubric_id: accurate_summary
    score: 0.8
    rationale: The title 'Long Short-Term Memory (LSTM)' accurately reflects the content
      of the body, but the description could be more precise in reflecting the specific
      contributions and applications mentioned in the raw note.
  - rubric_id: substantial
    score: 0.6
    rationale: While the draft concept provides some useful information about LSTMs,
      it feels a bit superficial and could benefit from additional details or examples
      to make it more substantial.
---

A Long Short-Term Memory (LSTM) is a type of recurrent neural network that can learn long-term dependencies. It was first introduced by Sepp Hochreiter and Jürgen Schmidhuber in their 1997 paper 'Long Short-Term Memory'. LSTMs are particularly useful for tasks such as speech recognition, language modeling, and predicting time series data.

## Related

- [Position-wise Feed-Forward Networks](/position-wise-feed-forward-networks.md) — Both LSTMs and position-wise feed-forward networks are types of recurrent neural network architectures.
- [Local Attention Mechanisms](/local-attention-mechanisms.md) — Local attention mechanisms, like LSTMs, can learn dependencies in sequential data.


Long-distance dependencies refer to the phenomenon where words or phrases are grammatically related across long stretches of text. This can be challenging for models to capture, as it often requires considering context beyond a local window.
- [Retrieval Augmented Generation (RAG)](/retrieval-augmented-generation-rag.md) — Both RAG and LSTM are techniques used in natural language processing and machine learning, making them relevant connections.
- [Sirius-LTG-UIO](/sirius-ltg-uio.md) — Both concepts involve the use of neural networks for tasks in natural language processing.

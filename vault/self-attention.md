---
type: Reference
title: Self-Attention
description: A type of attention mechanism where queries, keys, and values all come
  from the same source.
tags:
- attention
- self-supervised
eval:
  passed: true
  average_score: 0.75
  scores:
  - rubric_id: traceable
    score: 1.0
    rationale: All claims in the body are directly supported by the raw note.
  - rubric_id: not_verbatim
    score: 0.5
    rationale: The body does not add significant structure or clarity to the raw note;
      it merely restates the main idea with some minor variations.
  - rubric_id: accurate_summary
    score: 1.0
    rationale: The title and description accurately reflect what the body says.
  - rubric_id: substantial
    score: 0.5
    rationale: While the body is not entirely vague, it feels somewhat thin as a standalone
      entity; it could benefit from more detail or examples to make it more substantial.
---

In the Transformer, self-attention layers allow each position to attend to all positions in a previous layer. This is used in both the encoder and decoder.

The total computational complexity of a self-attention layer is typically faster than that of a recurrent layer when the sequence length n is smaller than the representation dimensionality d. A single convolutional layer with kernel width k < n does not connect all pairs of input and output positions, requiring a stack of O(n/k) or O(log k(n)) layers to achieve this.

Self-attention layers can connect all pairs of input and output positions, allowing for easier learning of long-range dependencies. This is particularly useful for tasks involving very long sequences, where restricting self-attention to considering only a neighborhood of size r in the input sequence centered around the respective output position can improve computational performance.

Individual attention heads in self-attention models can clearly learn to perform different tasks, and many appear to exhibit behavior related to the syntactic and semantic structure of sentences. This makes it easier to understand and analyze the results produced by these models.

The Transformer model is a type of neural network architecture that is particularly well-suited for sequence-to-sequence tasks, such as machine translation and text summarization. It uses self-attention mechanisms to directly access information from the entire input sequence, rather than relying on recurrent layers.

## Related

- [Local Attention Mechanisms](/local-attention-mechanisms.md) — Self-Attention is a type of attention mechanism, and Local Attention Mechanisms is another example of such mechanisms.
- [Transformer Variations](/transformer-variations.md) — The Transformer architecture uses Self-Attention layers, so linking to variations of the Transformer could be relevant for readers interested in the broader context of this concept.

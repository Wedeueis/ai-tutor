---
type: Metric
title: Position-wise Feed-Forward Networks
description: A fully connected feed-forward network applied to each position separately
  in a neural network.
tags:
- nlp
- neural-networks
eval:
  passed: true
  average_score: 0.85
  scores:
  - rubric_id: traceable
    score: 1.0
    rationale: All claims in the body are directly supported by the raw note.
  - rubric_id: not_verbatim
    score: 0.8
    rationale: The body does not simply repeat the raw note verbatim; it adds structure
      with headings and clarifies some points. However, some sentences are almost
      identical to their counterparts in the raw note.
  - rubric_id: accurate_summary
    score: 1.0
    rationale: The title and description accurately reflect what the body actually
      says.
  - rubric_id: substantial
    score: 0.6
    rationale: While the body provides some useful information, it is a bit thin and
      could be expanded upon with more details or examples to make it more substantial.
---

# Position-wise Feed-Forward Networks

In our encoder and decoder, each layer contains a fully connected feed-forward network. This is applied separately and identically to each position.

## Composition

This consists of two linear transformations with a ReLU activation in between. The linear transformations are the same across different positions, but use different parameters from layer to layer.

**Extended Neural GPU**

The Extended Neural GPU uses convolutional neural networks as the basic building block, computing hidden representations in parallel for all input and output positions. This approach reduces sequential computation but makes it more difficult to learn dependencies between distant positions.

## Related

- [Gated Recurrent Units](/gated-recurrent-units.md) — Both involve processing sequential information, albeit with different architectures.
- [Dot Product Properties](/dot-product-properties.md) — They both utilize dot product operations in the neural network architecture.


In our model, we share the same weight matrix between the two embedding layers and the pre-softmax linear transformation. This approach is similar to [30]. In the embedding layers, we multiply those weights by √d_model.


We use the usual learned linear transformation and softmax function to convert the decoder output to predicted next-token probabilities. This allows us to generate a probability distribution over possible tokens.


Sine-cosine positional encoding is a specific method used in positional encoding. It uses sinusoidal functions with wavelengths forming a geometric progression from 2π to 10000 · 2π, where pos is the position and i is the dimension.


Learned positional embeddings are a method used in some models to represent token positions. Instead of using a fixed formula, this approach learns the positional embeddings from the data.


We apply dropout to the output of each sub-layer, before it is added to the sub-layer input and normalized. In addition, we apply dropout to the sums of the embeddings and the positional encodings in both the encoder and decoder stacks.


Positional embeddings are a way to encode the position of elements in a sequence, such as text or audio. Unlike sinusoidal embeddings, positional embeddings directly represent each element's position, which can be beneficial for tasks like language modeling and machine translation.


Replacing sinusoidal positional encoding with learned positional embeddings can have a minimal impact on model quality, producing nearly identical results to the base model. This suggests that learned embeddings may be a viable alternative to traditional encoding methods.

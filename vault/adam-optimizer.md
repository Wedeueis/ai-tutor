---
type: Reference
title: Adam Optimizer
description: A popular stochastic gradient descent optimizer that adapts the learning
  rate for each parameter.
tags:
- optimization
- machine learning
eval:
  passed: true
  average_score: 0.7
  scores:
  - rubric_id: traceable
    score: 0.8
    rationale: Most claims in the body are traceable to the raw source material, but
      the formula is not decoded and mentioned as such.
  - rubric_id: not_verbatim
    score: 0.6
    rationale: The body does add some clarity by providing a brief summary of the
      Adam optimizer's properties, but it still closely repeats the raw note's content.
  - rubric_id: accurate_summary
    score: 1.0
    rationale: The title and description accurately reflect what the body actually
      says.
  - rubric_id: substantial
    score: 0.4
    rationale: While the body does provide some useful information about the Adam
      optimizer's hyperparameters, it is quite thin and could be expanded upon to
      make it more substantial.
---

The Adam optimizer is a popular stochastic gradient descent optimizer that adapts the learning rate for each parameter. It uses the first and second moments of the gradients to update the parameters, which can help improve convergence speed and stability. The Adam optimizer is defined by its hyperparameters: `β1` (first moment), `β2` (second moment), and `ϵ` (epsilon).

## Related

- [Training Regime](/training-regime.md) — The Adam optimizer is used in a specific training regime.
- [Attention Is All You Need](/attention-is-all-you-need.md) — The Adam optimizer was used in the original implementation of the Transformer model in Attention Is All You Need paper


The Adam optimizer is a type of stochastic gradient descent optimizer used for training neural networks. It was first introduced by Diederik Kingma and Jimmy Ba in their 2015 paper 'Adam: A Method for Stochastic Optimization'. The main idea behind this optimizer is to adaptively adjust the learning rate based on the magnitude of the gradients.

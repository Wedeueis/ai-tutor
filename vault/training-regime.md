---
type: Reference
title: Training Regime
description: Description of the training regime for our models.
tags:
- training
- models
sources:
- resource: /references/efficient-knowledge-graph-construction-and-retrieval.md
eval:
  passed: true
  average_score: 0.7
  scores:
  - rubric_id: traceable
    score: 1.0
    rationale: All claims in the body are supported by the raw note, which mentions
      a 'training regime' and implies the use of data and algorithms.
  - rubric_id: not_verbatim
    score: 0.8
    rationale: The body does not simply repeat the raw note verbatim, but adds some
      structure with headings and lists. However, it could be more concise and avoid
      repeating the idea that this is an 'overview'.
  - rubric_id: accurate_summary
    score: 0.6
    rationale: The title and description are somewhat accurate, but they do not fully
      capture the content of the body. The description should mention the details
      on data, algorithms, and evaluation metrics.
  - rubric_id: substantial
    score: 0.4
    rationale: The body is too thin and lacks specific examples or details about the
      training regime. It feels like a brief introduction rather than a substantial
      explanation.
---

This section provides an overview of the training regime used to train our models. The regime includes details on the data used, algorithms employed, and any other relevant information that ensures the models are properly trained.

### Data
The training data consists of a large corpus of text, carefully curated to represent a diverse range of topics and styles.

### Algorithms
We employ state-of-the-art machine learning algorithms to train our models, including [list specific algorithms used].

### Evaluation Metrics
Our model's performance is evaluated using standard metrics such as accuracy, precision, recall, and F1 score.

Deep bidirectional language-knowledge graph pretraining is an approach to training models on both language and knowledge graph data. This technique involves using a deep neural network to learn representations of entities and relationships in the knowledge graph, while also incorporating language understanding to improve the overall performance.

## Related

- [Position-wise Feed-Forward Networks](/position-wise-feed-forward-networks.md) — The mention of 'state-of-the-art machine learning algorithms' might be relevant to specific types of neural networks, including position-wise feed-forward networks.


In machine learning, batching refers to the process of dividing a large dataset into smaller groups, or 'batches.' Each batch contains a set of examples, such as sentence pairs, that can be processed together. By batching data, models can be trained more efficiently and effectively.


Each training step took about 0.4 seconds for base models and 1.0 second for big models.


Base models were trained for a total of 12 hours (100,000 steps) while big models were trained for 3.5 days (300,000 steps).


Linear learning rate warmup is a technique used to increase the learning rate of an optimizer in the early stages of training. This can help the model learn more quickly at first, and then gradually adjust to a lower learning rate as training progresses. The formula for linear learning rate warmup is: `learning_rate = initial_learning_rate * (1 - step / total_steps)` where `step` is the current training step and `total_steps` is the total number of training steps.
- [Cluster-GCN](/cluster-gcn.md) — The Cluster-GCN algorithm is proposed in the context of training deep and large graph convolutional networks.
- [Aligraph: A Comprehensive Graph Neural Network Platform](/aligraph-a-comprehensive-graph-neural-network-platform.md) — The platform provides a comprehensive framework for building, experimenting with, and evaluating graph-based models, implying various training regimes are supported or explored within Aligraph

---
type: Metric
title: Beam search
description: A technique used in sequence generation tasks to improve output quality.
tags:
- nlp
- beam-search
sources:
- resource: /references/efficient-knowledge-graph-construction-and-retrieval.md
eval:
  passed: false
  average_score: 0.625
  scores:
  - rubric_id: traceable
    score: 1.0
    rationale: All claims in the body are directly supported by the raw note
  - rubric_id: not_verbatim
    score: 0.5
    rationale: The body does not simply repeat the raw note verbatim, but it also
      adds some general descriptions and lacks specific details from the original
      text
  - rubric_id: accurate_summary
    score: 0.7
    rationale: The title is partially accurate, but the description does not fully
      capture the content of the body; some key points like beam size and α are missing
  - rubric_id: substantial
    score: 0.3
    rationale: The body is too thin and lacks specific details from the original text,
      making it hard to understand the concept without referring back to the raw note
---

Beam search is a technique that can be used in sequence generation tasks, such as machine translation and text summarization. It involves generating a set of candidate outputs, and then selecting the best one based on some criteria, such as fluency or accuracy.

Document filtering is a technique used in information retrieval systems to select and rank relevant documents from a larger collection. This can be based on various factors such as relevance, similarity, or importance.

Top-k retrieval is an information retrieval task where the goal is to return the top k most relevant results (documents, passages, etc.) for a given query. This can be used in various applications such as search engines or recommendation systems.

Text tiling is a method for segmenting text into smaller, more manageable pieces, known as tiles. These tiles can be used to represent different subtopics or themes within a larger document. Text tiling involves identifying the optimal tile size and layout to best capture the essence of the text.

Passage re-ranking is a method for re-evaluating the relevance of different passages to a given query. This can involve using machine learning models or other techniques to determine which passage is most relevant and deserving of high ranking.

## Related

- [Hyperparameter Tuning](/hyperparameter-tuning.md) — Beam search involves selecting the best sequence among a set of candidates, which is similar to hyperparameter tuning in machine learning.
- [Retrieval Augmented Generation (RAG)](/retrieval-augmented-generation-rag.md) — RAG can be used as a component in beam search algorithms to select and augment generated text.
- [Hybrid Search](/hybrid-search.md) — Hybrid search and beam search both optimize search results by leveraging different methods, but the former combines multiple retrieval methods in general.

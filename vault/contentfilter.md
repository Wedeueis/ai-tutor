---
type: Metric
title: ContentFilter
description: Filters out sentences lacking verbs in their syntactic structure.
tags:
- knowledge-graph
- content-filtering
sources:
- resource: /references/efficient-knowledge-graph-construction-and-retrieval.md
eval:
  passed: true
  average_score: 0.7
  scores:
  - rubric_id: traceable
    score: 1.0
    rationale: The draft concept accurately describes the function of ContentFilter,
      which is to filter out sentences lacking verbs in their syntactic structure,
      as mentioned in the raw note.
  - rubric_id: not_verbatim
    score: 0.8
    rationale: While the draft concept adds a brief summary, it lacks the specific
      details and context provided in the raw note, such as the use of SpaCy for parsing
      and part-of-speech tags to filter out sentences lacking verbs.
  - rubric_id: accurate_summary
    score: 0.6
    rationale: The title 'ContentFilter' is accurate, but the description could be
      more precise in reflecting what the body actually says. The description focuses
      on the filtering of sentences lacking verbs, whereas the raw note mentions efficient
      pruning and reduced LLM calls as well.
  - rubric_id: substantial
    score: 0.4
    rationale: The draft concept is too brief to be considered substantial on its
      own. It lacks sufficient detail and context to convey any real, standalone insight
      about the ContentFilter component. The raw note, however, provides a more comprehensive
      explanation of the content filtering process.
---

The ContentFilter takes output from the SentenceSegmenter and filters out sentences that do not have verbs in their syntactic structure. This allows for efficient pruning of content and reduces the amount of LLM calls during downstream entity/relation extraction.


We use the RelationEntityFilter to ensure extracted entities and relations conform to an established schema.

---
type: Reference
title: Challenges and Limitations
description: The limitations of current GraphRAG systems and potential areas for future
  work.
tags:
- challenges
- limitations
sources:
- resource: /references/efficient-knowledge-graph-construction-and-retrieval.md
eval:
  passed: false
  average_score: 0.6
  scores:
  - rubric_id: traceable
    score: 0.8
    rationale: Most claims are supported by the raw note, but one specific limitation
      (missing implicit relations) is not explicitly mentioned
  - rubric_id: not_verbatim
    score: 0.6
    rationale: The body does not simply repeat the raw note verbatim, but it's more
      of a summary than a restructured or clarified version
  - rubric_id: accurate_summary
    score: 0.4
    rationale: The title and description do not accurately reflect what the body actually
      says (it mentions limitations, but the focus is on scalability)
  - rubric_id: substantial
    score: 0.6
    rationale: The body contains a couple of useful points about potential areas for
      future work, but it's relatively thin and could be fleshed out
---

Our approach eliminates one significant bottleneck, but may miss context-dependent or implicit relations not directly expressed in surface syntax. Its generalizability to other settings remains an open question.

## Related

- [Dependency Parsing](/dependency-parsing.md) — Both concepts deal with the limitations and potential areas of improvement in natural language processing tasks.
- [EntityRelationNormalizer](/entityrelationnormalizer.md) — Entity relation normalization is a related task that can potentially be improved upon by overcoming the challenges mentioned in this concept.

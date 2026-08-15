"""PrerequisiteJudgementSkillPort adapter: a local chat model scores each
candidate edge against the prerequisite rubrics.

**One call per candidate**, not one call for all of them. RF1.2 specifies a
per-*edge* gate, and asking a small local model to return a nested
target-by-rubric structure in a single response is the shape they get wrong
most often. One call per candidate keeps the response in the same flat
rubric-array shape `OllamaQualityEvalSkill` already proves out, at the cost of
up to five extra calls per draft — cheap next to the precision this feature is
graded on (RF1.3's 0.9 bar)."""

from __future__ import annotations

from pipeline.adapters.ollama.client import OllamaClient
from pipeline.domain.agent import DraftConcept
from pipeline.domain.eval import Rubric, RubricScore
from pipeline.domain.prerequisites import PrerequisiteAssessment, PrerequisiteCandidate

_PROMPT = """You judge whether one wiki concept is a genuine PREREQUISITE of another
— something a learner must already understand before the other is followable at
all. Most pairs of related concepts are NOT prerequisites. Be strict: when in
doubt, score low. A wrong prerequisite sends someone to study something they do
not need, and nothing downstream will catch it.

Score the claim "SOURCE requires TARGET" against EACH rubric below
independently, from 0.0 (fails the criterion) to 1.0 (fully meets it).

Rubrics (id: criterion):
{rubrics}

SOURCE concept (the dependent one):
title: {source_title}
description: {source_description}
body: {source_body}

TARGET concept (the possible prerequisite):
id: {target_id}
title: {target_title}
description: {target_description}

Respond with ONLY a JSON array, one entry per rubric id above:
[{{"rubric_id": "<id>", "score": <0.0-1.0>, "rationale": "<short reason>"}}, ...]
"""


class OllamaPrerequisiteJudgementSkill:
    def __init__(self, client: OllamaClient, model: str) -> None:
        self._client = client
        self._model = model

    def judge(
        self,
        draft: DraftConcept,
        candidates: list[PrerequisiteCandidate],
        rubrics: list[Rubric],
    ) -> list[PrerequisiteAssessment]:
        if not rubrics or not candidates:
            return []

        rubrics_text = "\n".join(
            f"- {r.rubric_id}: {r.rubric_content.text_property}" for r in rubrics
        )
        return [
            self._judge_one(draft, candidate, rubrics, rubrics_text)
            for candidate in candidates
        ]

    def _judge_one(
        self,
        draft: DraftConcept,
        candidate: PrerequisiteCandidate,
        rubrics: list[Rubric],
        rubrics_text: str,
    ) -> PrerequisiteAssessment:
        prompt = _PROMPT.format(
            rubrics=rubrics_text,
            source_title=draft.frontmatter.title or "",
            source_description=draft.frontmatter.description or "",
            source_body=draft.body,
            target_id=candidate.concept_id,
            target_title=candidate.title or "",
            target_description=candidate.description or "",
        )
        parsed = self._client.generate_json(self._model, prompt)
        entries = parsed if isinstance(parsed, list) else [parsed]

        by_id: dict[str, RubricScore] = {}
        for entry in entries:
            if not isinstance(entry, dict) or "rubric_id" not in entry:
                continue
            score = entry.get("score")
            by_id[entry["rubric_id"]] = RubricScore(
                rubric_id=entry["rubric_id"],
                score=float(score) if score is not None else None,
                rationale=entry.get("rationale"),
            )

        # One entry per rubric, `score=None` where the model didn't answer.
        # `select_prerequisites` reads that None as "incomplete" and caps the
        # edge at `may_require::` — a skipped criterion is not a cleared one.
        scores = [by_id.get(r.rubric_id, RubricScore(rubric_id=r.rubric_id)) for r in rubrics]
        rationale = "; ".join(s.rationale for s in scores if s.rationale)
        return PrerequisiteAssessment(
            target_id=candidate.concept_id, scores=scores, rationale=rationale
        )

"""QualityEvalSkillPort adapter: the configured chat model scores a draft concept against
each rubric independently (one LLM call scores every rubric at once), given the
original raw text for grounding checks. Pass/fail is decided elsewhere —
deterministically, from the scores (see domain/eval.py's aggregate_scores)."""

from __future__ import annotations

from pipeline.application.ports.chat_model import ChatModelPort
from pipeline.domain.agent import DraftConcept
from pipeline.domain.eval import Rubric, RubricScore

_PROMPT = """You are a strict quality judge for a personal knowledge-base wiki. A
draft concept was extracted from a raw note by another model. Score it against
EACH rubric below independently, from 0.0 (fails) to 1.0 (fully meets it). Be
strict: penalize fabricated claims not grounded in the raw note, content that's
too thin/vague to be useful, or a body that just repeats the raw note verbatim
without adding structure or clarity.

Rubrics (id: criterion):
{rubrics}

Raw note:
---
{raw_content}
---

Draft concept:
title: {title}
description: {description}
body: {body}

Respond with ONLY a JSON array, one entry per rubric id above:
[{{"rubric_id": "<id>", "score": <0.0-1.0>, "rationale": "<short reason>"}}, ...]
"""


class QualityEvalSkill:
    def __init__(self, client: ChatModelPort, model: str) -> None:
        self._client = client
        self._model = model

    def evaluate(
        self, draft: DraftConcept, rubrics: list[Rubric], raw_content: str
    ) -> list[RubricScore]:
        if not rubrics:
            return []

        rubrics_text = "\n".join(
            f"- {r.rubric_id}: {r.rubric_content.text_property}" for r in rubrics
        )
        prompt = _PROMPT.format(
            rubrics=rubrics_text,
            raw_content=raw_content,
            title=draft.frontmatter.title or "",
            description=draft.frontmatter.description or "",
            body=draft.body,
        )
        # Array-shaped, like extraction: one entry per rubric. A model that
        # scored exactly one rubric sometimes returns the bare object instead.
        parsed = self._client.generate_json(self._model, prompt)
        entries = parsed if isinstance(parsed, list) else [parsed]

        by_id = {}
        for entry in entries:
            if not isinstance(entry, dict) or "rubric_id" not in entry:
                continue
            score = entry.get("score")
            by_id[entry["rubric_id"]] = RubricScore(
                rubric_id=entry["rubric_id"],
                score=float(score) if score is not None else None,
                rationale=entry.get("rationale"),
            )

        return [by_id.get(r.rubric_id, RubricScore(rubric_id=r.rubric_id)) for r in rubrics]

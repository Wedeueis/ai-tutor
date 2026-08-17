"""`AssessmentSkillPort` over LiteLLM.

**LiteLLM rather than an Ollama HTTP client of our own**, because NFR1's
obligation is to keep the model provider behind a configurable seam and this
makes that seam a single model string: `ollama_chat/qwen3.5:4b` today,
`openrouter/...` the day #19 lands, with nothing here to change. It is already
a dependency — ADK reaches the same models through it — so the two paths cannot
end up talking to different providers by accident. The package is named for the
role rather than for LiteLLM, because the provider behind it is the part meant
to change.

Prompt shape mirrors `pipeline`'s skills: one call scores every rubric at once,
returning a JSON array, and **no call ever returns a verdict**. The rating is
domain logic (`rating_for`), and a port that could return one would make that
unenforceable.
"""

from __future__ import annotations

import logging
from typing import Any

from litellm import acompletion

from tutor.adapters.llm._json import as_array, as_object
from tutor.application.ports.outbound.assessment import Assessment
from tutor.application.ports.outbound.vault import Concept
from tutor.domain.assessment import Rubric, RubricContent, RubricScore
from tutor.domain.depth import DepthLevel, requirement_for

logger = logging.getLogger(__name__)

_GENERATE = """You are writing one review question for a learner returning to
their own knowledge vault. They wrote or saved this concept themselves; they
have met it before.

Write a question that makes them RETRIEVE the concept, not recognise it. No
yes/no questions, nothing answerable by repeating the title back.

Depth target: {level} — {description}
{level_guidance}

Ground the question strictly in the concept below. Do not ask about anything it
does not contain.

concept id: {concept_id}
title: {title}
description: {description_text}
body:
---
{body}
---

Respond with ONLY a JSON object:
{{"question": "<the question>",
  "rubrics": [{{"rubric_id": "<short-slug>", "criterion": "<what a good answer must contain>"}}, ...]}}

Give 2 to 4 rubrics. Each must be checkable against the concept's own content —
a criterion nobody could verify from the concept is not a criterion.
"""

_LEVEL_GUIDANCE = {
    DepthLevel.AWARE: (
        "Ask what it is and what it is for. Recognising it and placing it "
        "correctly is enough."
    ),
    DepthLevel.WORKING: (
        "Ask them to use it: apply it to a case, or say when it applies and "
        "when it does not."
    ),
    DepthLevel.SPECIALIST: (
        "Ask them to explain it in their own words, including why it works "
        "the way it does, or what breaks without it."
    ),
}

_GRADE = """You are grading a learner's answer to a review question. Score it
against EACH rubric independently, from 0.0 (does not meet it) to 1.0 (fully
meets it).

Judge only what the rubric asks. Do not penalise an answer for omitting
something no rubric mentions, and do not reward length. An answer in the
learner's own words that is correct scores full marks even if it uses different
vocabulary from the source.

If a rubric cannot be judged from this answer at all, return null for its
score rather than 0.

Question:
{question}

Rubrics (id: criterion):
{rubrics}

Learner's answer:
---
{answer}
---

Respond with ONLY a JSON array, one entry per rubric id above:
[{{"rubric_id": "<id>", "score": <0.0-1.0 or null>, "rationale": "<short reason>"}}, ...]
"""


class LiteLlmAssessmentSkill:
    def __init__(
        self, model: str, api_base: str | None = None, temperature: float = 0.2
    ) -> None:
        self._model = model
        self._api_base = api_base
        self._temperature = temperature

    async def generate(self, concept: Concept, level: DepthLevel) -> Assessment:
        """Written from the concept's content **as it is now** (RF4.3).

        A model that returns nothing usable still has to produce a question, or
        the review cannot happen — so there is a fallback question grounded in
        the concept's own title. It is a poor question, and it is honest about
        being one; failing the whole session instead would be worse."""
        requirement = requirement_for(level)
        raw = await self._complete(
            _GENERATE.format(
                level=level.value,
                description=requirement.description,
                level_guidance=_LEVEL_GUIDANCE[level],
                concept_id=concept.concept_id,
                title=concept.title or concept.concept_id,
                description_text=concept.description or "",
                body=concept.body,
            )
        )
        payload = as_object(raw)
        question = str(payload.get("question") or "").strip()
        rubrics = _rubrics(payload.get("rubrics"))
        if not question or not rubrics:
            logger.warning(
                "assessment generation for %s came back unusable — falling back",
                concept.concept_id,
            )
            return _fallback(concept, level)
        return Assessment(
            concept_id=concept.concept_id, question=question, rubrics=rubrics
        )

    async def grade(self, assessment: Assessment, answer: str) -> list[RubricScore]:
        """One score per rubric, and never a verdict.

        A rubric the model did not return comes back with `score=None`, so the
        rollup drops it rather than counting it as a zero — the grader's
        silence is not the learner's failure. If it returned nothing at all,
        every rubric is unjudged, `aggregate_scores` reports `graded=False`,
        and `rating_for` refuses rather than inventing a lapse."""
        raw = await self._complete(
            _GRADE.format(
                question=assessment.question,
                rubrics="\n".join(
                    f"- {rubric.rubric_id}: {rubric.rubric_content.text_property}"
                    for rubric in assessment.rubrics
                ),
                answer=answer,
            )
        )
        returned = {
            str(entry["rubric_id"]): entry
            for entry in as_array(raw)
            if isinstance(entry, dict) and "rubric_id" in entry
        }
        return [
            _score(rubric.rubric_id, returned.get(rubric.rubric_id))
            for rubric in assessment.rubrics
        ]

    async def _complete(self, prompt: str) -> str:
        response = await acompletion(
            model=self._model,
            api_base=self._api_base,
            temperature=self._temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return str(response["choices"][0]["message"]["content"] or "")


def _fallback(concept: Concept, level: DepthLevel) -> Assessment:
    """The question to ask when generation failed. Deliberately generic, and
    the rubric says so, so a run of these is visible in the log rather than
    looking like ordinary reviews."""
    name = concept.title or concept.concept_id
    return Assessment(
        concept_id=concept.concept_id,
        question=f"Explain {name} in your own words, as if to someone who has not met it.",
        rubrics=[
            Rubric(
                rubric_id="fallback-substance",
                rubric_content=RubricContent(
                    text_property=(
                        "The answer describes what the concept is and what it is for, "
                        "consistently with the vault's content."
                    )
                ),
                description=f"Generated without a model, at depth {level.value}.",
            )
        ],
    )


def _rubrics(raw: Any) -> list[Rubric]:
    if not isinstance(raw, list):
        return []
    rubrics = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue
        criterion = str(entry.get("criterion") or "").strip()
        if not criterion:
            continue
        rubrics.append(
            Rubric(
                rubric_id=str(entry.get("rubric_id") or f"r{index + 1}"),
                rubric_content=RubricContent(text_property=criterion),
            )
        )
    return rubrics


def _score(rubric_id: str, entry: Any) -> RubricScore:
    """Unjudged unless the model returned a number in range. A score of 3.0 or
    "good" is a malformed answer, not a perfect one."""
    if not isinstance(entry, dict):
        return RubricScore(rubric_id=rubric_id, rationale="not returned by the grader")
    value = entry.get("score")
    rationale = entry.get("rationale")
    if not isinstance(value, int | float) or isinstance(value, bool):
        return RubricScore(
            rubric_id=rubric_id,
            rationale=str(rationale) if rationale else "no usable score returned",
        )
    return RubricScore(
        rubric_id=rubric_id,
        score=min(max(float(value), 0.0), 1.0),
        rationale=str(rationale) if rationale else None,
    )



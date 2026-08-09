"""EntityDisambiguationSkillPort adapter: asks a local chat model whether a draft
concept is the same entity as one of the candidates surfaced by vector search."""

from __future__ import annotations

from pipeline.adapters.ollama.client import OllamaClient
from pipeline.domain.agent import CandidateMatch, DisambiguationVerdict, DraftConcept

_PROMPT = """You maintain a personal knowledge-base wiki and must avoid duplicate entries.

A new draft concept:
title: {title}
description: {description}
body: {body}

Candidate existing concepts that may already cover the same thing (id, similarity score):
{candidates}

Decide: is the draft the SAME concept as one of these candidates (should be merged
into it), or is it genuinely NEW (should become its own concept)?

Respond with ONLY a JSON object: {{"same_as": "<candidate id or null>", "confidence": <0.0-1.0>, "rationale": "<short reason>"}}
"""


class OllamaEntityDisambiguationSkill:
    def __init__(self, client: OllamaClient, model: str) -> None:
        self._client = client
        self._model = model

    def disambiguate(
        self, draft: DraftConcept, candidates: list[CandidateMatch]
    ) -> DisambiguationVerdict:
        candidates_text = "\n".join(
            f"- {c.concept_id} (score={c.score:.2f})" for c in candidates
        )
        prompt = _PROMPT.format(
            title=draft.frontmatter.title or "",
            description=draft.frontmatter.description or "",
            body=draft.body,
            candidates=candidates_text,
        )
        parsed = self._client.generate_json(self._model, prompt)

        same_as_raw = parsed.get("same_as")
        return DisambiguationVerdict(
            same_as=_resolve_id(same_as_raw, candidates),
            confidence=float(parsed.get("confidence", 0.0)),
            rationale=parsed.get("rationale", ""),
        )


def _resolve_id(raw_id, candidates: list[CandidateMatch]):
    if not raw_id:
        return None
    for candidate in candidates:
        if str(candidate.concept_id) == str(raw_id):
            return candidate.concept_id
    return None

"""RelatednessSkillPort adapter: asks a local chat model which existing
concepts (surfaced by vector search, already ruled out as the same entity)
are genuinely related enough to link to."""

from __future__ import annotations

from pipeline.adapters.ollama.client import OllamaClient
from pipeline.domain.agent import (
    DraftConcept,
    RelatedConcept,
    RelatednessCandidate,
    RelatednessVerdict,
)

_PROMPT = """You maintain a personal knowledge-base wiki. New concepts should link to
existing concepts they are genuinely related to, so clusters of knowledge are
easy to navigate — but you must not link things that are merely superficially
similar.

A new draft concept:
title: {title}
description: {description}
body: {body}

Candidate existing concepts that might be genuinely related (id, title):
{candidates}

Decide which candidates, if any, are genuinely related to the draft (not the
same entity — that has already been ruled out — but worth a reader following
a link to). Judge relatedness from the actual content of the title/body only
— you are not given a similarity score, and "these seem similar" is not a
reason; name the real conceptual connection. For each one you pick, give a
short one-sentence reason.

Respond with ONLY a JSON object:
{{"related": [{{"concept_id": "<id>", "reason": "<short reason>"}}, ...]}}
Use an empty list if none are genuinely related.
"""


class OllamaRelatednessSkill:
    def __init__(self, client: OllamaClient, model: str) -> None:
        self._client = client
        self._model = model

    def judge(
        self, draft: DraftConcept, candidates: list[RelatednessCandidate]
    ) -> RelatednessVerdict:
        if not candidates:
            return RelatednessVerdict(related=[])

        candidates_text = "\n".join(f"- {c.concept_id} | {c.title or ''}" for c in candidates)
        prompt = _PROMPT.format(
            title=draft.frontmatter.title or "",
            description=draft.frontmatter.description or "",
            body=draft.body,
            candidates=candidates_text,
        )
        parsed = self._client.generate_json(self._model, prompt)

        related: list[RelatedConcept] = []
        for entry in parsed.get("related") or []:
            concept_id = _resolve_id(entry.get("concept_id"), candidates)
            if concept_id is None:
                continue
            title = next((c.title for c in candidates if c.concept_id == concept_id), None)
            related.append(
                RelatedConcept(concept_id=concept_id, title=title, reason=entry.get("reason", ""))
            )
        return RelatednessVerdict(related=related)


def _resolve_id(raw_id, candidates: list[RelatednessCandidate]):
    if not raw_id:
        return None
    for candidate in candidates:
        if str(candidate.concept_id) == str(raw_id):
            return candidate.concept_id
    return None

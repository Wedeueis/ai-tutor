"""DomainClassificationSkillPort adapter: asks the configured chat model which existing
Domain (if any) a draft concept belongs to. Low confidence maps to `domain=None`
— Domains stay human-curated, unlike `type`, which is cheap to mint."""

from __future__ import annotations

from pipeline.application.ports.chat_model import ChatModelPort
from pipeline.domain.agent import DomainCandidate, DomainClassificationVerdict, DraftConcept
from pipeline.domain.concept import ConceptId

_PROMPT = """You maintain a personal knowledge-base wiki organized into Domains —
coherent areas like "Coffee" or "Finance". Decide which existing Domain (if any)
this draft concept belongs to. Only pick a Domain if it's a clear, confident fit;
if nothing fits well, say so rather than forcing a match — a human will triage it.

Existing Domains (id, title, description):
{domains}

Draft concept:
title: {title}
description: {description}
body: {body}

Respond with ONLY a JSON object: {{"domain": "<domain id or null>", "confidence": <0.0-1.0>, "rationale": "<short reason>"}}
"""


class DomainClassificationSkill:
    def __init__(self, client: ChatModelPort, model: str) -> None:
        self._client = client
        self._model = model

    def classify(
        self, draft: DraftConcept, candidates: list[DomainCandidate]
    ) -> DomainClassificationVerdict:
        if not candidates:
            return DomainClassificationVerdict(domain=None, confidence=0.0, rationale="no domains exist yet")

        domains_text = "\n".join(
            f"- {c.concept_id} | {c.title or ''} | {c.description or ''}" for c in candidates
        )
        prompt = _PROMPT.format(
            domains=domains_text,
            title=draft.frontmatter.title or "",
            description=draft.frontmatter.description or "",
            body=draft.body,
        )
        parsed = self._client.generate_json_object(self._model, prompt)

        return DomainClassificationVerdict(
            domain=_resolve_id(parsed.get("domain"), candidates),
            confidence=float(parsed.get("confidence", 0.0)),
            rationale=parsed.get("rationale", ""),
        )


def _resolve_id(raw_id, candidates: list[DomainCandidate]) -> ConceptId | None:
    if not raw_id:
        return None
    for candidate in candidates:
        if str(candidate.concept_id) == str(raw_id):
            return candidate.concept_id
    return None

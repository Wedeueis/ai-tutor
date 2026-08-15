"""CategoryClassificationSkillPort adapter: asks a local chat model which
existing Categories (if any) a draft belongs to, or whether new ones should
be minted — the finer-grained tier underneath `type: Domain`."""

from __future__ import annotations

from pipeline.adapters.ollama.client import OllamaClient
from pipeline.domain.agent import CategoryCandidate, CategoryClassificationVerdict, DraftConcept
from pipeline.domain.concept import ConceptId

_PROMPT = """You maintain a personal knowledge-base wiki organized into Domains, and
within each Domain, finer-grained Categories (like Wikipedia's category system) —
e.g. Domain "Coffee" might have Categories "Brewing Methods", "Equipment". Decide
which existing Categories (zero or more) this draft concept belongs to. Reuse an
existing Category whenever the draft plausibly fits one, rather than minting a
near-duplicate; only propose new Category titles when nothing existing fits.

Existing Categories in this domain (id, title):
{categories}

Draft concept:
title: {title}
description: {description}
body: {body}

Respond with ONLY a JSON object: {{"categories": ["<existing category id>", ...], "new_categories": ["<new category title>", ...], "confidence": <0.0-1.0>, "rationale": "<short reason>"}}
"""


class OllamaCategoryClassificationSkill:
    def __init__(self, client: OllamaClient, model: str) -> None:
        self._client = client
        self._model = model

    def classify(
        self, draft: DraftConcept, known_categories: list[CategoryCandidate]
    ) -> CategoryClassificationVerdict:
        categories_text = (
            "\n".join(f"- {c.concept_id} | {c.title or ''}" for c in known_categories)
            or "(none yet)"
        )
        prompt = _PROMPT.format(
            categories=categories_text,
            title=draft.frontmatter.title or "",
            description=draft.frontmatter.description or "",
            body=draft.body,
        )
        parsed = self._client.generate_json_object(self._model, prompt)

        return CategoryClassificationVerdict(
            categories=_resolve_ids(parsed.get("categories") or [], known_categories),
            new_categories=[str(t) for t in parsed.get("new_categories") or []],
            confidence=float(parsed.get("confidence", 0.0)),
            rationale=parsed.get("rationale", ""),
        )


def _resolve_ids(raw_ids: list, candidates: list[CategoryCandidate]) -> list[ConceptId]:
    known = {str(c.concept_id): c.concept_id for c in candidates}
    return [known[str(raw_id)] for raw_id in raw_ids if str(raw_id) in known]

"""TypeClassificationSkillPort adapter: resolves a draft's `type` against the
vault's existing type vocabulary, via a local chat model."""

from __future__ import annotations

from pipeline.adapters.ollama.client import OllamaClient
from pipeline.domain.agent import DraftConcept, TypeClassificationVerdict

_PROMPT = """You maintain a personal knowledge-base wiki that uses a `type` field
(e.g. "Playbook", "Metric", "Reference") to classify each entry (OKF spec §4.1).
Reuse an existing type whenever the draft plausibly fits one, rather than minting
a near-duplicate name; only propose a new type when nothing existing fits.

Types already in use: {known_types}

Draft concept:
title: {title}
description: {description}
body: {body}

Respond with ONLY a JSON object: {{"resolved_type": "<type name>", "is_new_type": <true|false>, "rationale": "<short reason>"}}
"""


class OllamaTypeClassificationSkill:
    def __init__(self, client: OllamaClient, model: str) -> None:
        self._client = client
        self._model = model

    def classify(
        self, draft: DraftConcept, known_types: list[str]
    ) -> TypeClassificationVerdict:
        prompt = _PROMPT.format(
            known_types=", ".join(known_types) or "(none yet)",
            title=draft.frontmatter.title or "",
            description=draft.frontmatter.description or "",
            body=draft.body,
        )
        parsed = self._client.generate_json(self._model, prompt)
        resolved_type = parsed.get("resolved_type") or "Unclassified"
        return TypeClassificationVerdict(
            resolved_type=resolved_type,
            is_new_type=bool(parsed.get("is_new_type", resolved_type not in known_types)),
            rationale=parsed.get("rationale", ""),
        )

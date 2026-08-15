"""ExtractionSkillPort adapter: the configured chat model turns raw text into draft OKF
concepts. `type` is left as a placeholder — TypeClassificationSkillPort resolves
it against the vault's existing type vocabulary downstream."""

from __future__ import annotations

from pipeline.application.ports.chat_model import ChatModelPort
from pipeline.domain.agent import DraftConcept
from pipeline.domain.concept import Frontmatter
from pipeline.domain.raw_material import RawItem

_PLACEHOLDER_TYPE = "Unclassified"

_PROMPT = """You turn raw personal notes into knowledge-base entries.

Read the note below and extract one or more distinct, self-contained concepts
worth keeping as their own wiki entry. For each concept, produce a JSON object with:
- "title": short display name
- "description": one-sentence summary
- "tags": array of a few short lowercase tags
- "body": the concept's markdown body, written clearly, based on the note

Respond with ONLY a JSON array of these objects, nothing else.

Note:
---
{content}
---
"""


class ExtractionSkill:
    def __init__(self, client: ChatModelPort, model: str) -> None:
        self._client = client
        self._model = model

    def extract(self, raw: RawItem) -> list[DraftConcept]:
        prompt = _PROMPT.format(content=raw.content)
        parsed = self._client.generate_json(self._model, prompt)
        # The prompt asks for an array, but a model that found exactly one
        # concept often returns the bare object instead.
        entries = [parsed] if isinstance(parsed, dict) else parsed

        drafts = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue  # a stray scalar in the array is not a concept
            frontmatter = Frontmatter(
                type=_PLACEHOLDER_TYPE,
                title=entry.get("title"),
                description=entry.get("description"),
                tags=list(entry.get("tags") or []),
            )
            drafts.append(
                DraftConcept(
                    frontmatter=frontmatter,
                    body=entry.get("body", ""),
                    source_raw_id=raw.id,
                )
            )
        return drafts

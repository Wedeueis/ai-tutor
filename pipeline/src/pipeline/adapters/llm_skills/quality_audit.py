"""QualityAuditSkillPort adapter: asks the configured chat model whether an
already-published concept stands alone as genuinely useful, or is a thin
fragment of something larger (e.g. one row of a table split into its own
concept) that reads as fine prose but conveys little real knowledge."""

from __future__ import annotations

from pipeline.application.ports.chat_model import ChatModelPort
from pipeline.domain.agent import QualityAuditVerdict
from pipeline.domain.concept import Concept

_PROMPT = """You are auditing an existing personal knowledge-base wiki for low-quality
entries. Most concepts are FINE. A concept is standalone quality if a reader
who has never seen its source could understand what the topic actually IS or
how it works — even if it's short, even if it's one of several concepts
extracted from the same paper/document, even if it mentions related ideas.
None of that is a defect by itself.

Only flag a concept as LOW QUALITY if it is genuinely useless read on its
own — for example:
- It's a bare fragment of a table/list: numbers or values with essentially
  no explanation of what they mean or why they matter (e.g. "these values
  fall between 4 and 8").
- It only states that something exists ("this is a data point", "this table
  contains values") without ever explaining what it IS.
- Its title/description promise one thing but the body is empty, circular,
  or just restates the title.

Do NOT flag a concept merely because it's short, narrow, or references other
concepts — a correct, self-contained explanation of one specific idea is
exactly what a good concept looks like, regardless of length.

Concept:
title: {title}
description: {description}
body: {body}

Respond with ONLY a JSON object:
{{"standalone_quality": true|false, "reason": "<short reason, quoting the
specific problem in the body if false>"}}
"""


class QualityAuditSkill:
    def __init__(self, client: ChatModelPort, model: str) -> None:
        self._client = client
        self._model = model

    def judge(self, concept: Concept) -> QualityAuditVerdict:
        prompt = _PROMPT.format(
            title=concept.frontmatter.title or "",
            description=concept.frontmatter.description or "",
            body=concept.body,
        )
        parsed = self._client.generate_json_object(self._model, prompt)
        return QualityAuditVerdict(
            standalone_quality=bool(parsed.get("standalone_quality", True)),
            reason=parsed.get("reason", ""),
        )

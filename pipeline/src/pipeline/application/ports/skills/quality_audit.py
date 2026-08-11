from __future__ import annotations

from typing import Protocol

from pipeline.domain.agent import QualityAuditVerdict
from pipeline.domain.concept import Concept


class QualityAuditSkillPort(Protocol):
    """LLM-backed: judges whether an already-published concept stands alone
    as genuinely useful, or is a thin/vacuous fragment — the retroactive
    counterpart to QualityEvalSkillPort, which only judges fresh drafts
    against their raw source. Used by AuditConceptQuality (`pipeline
    audit`)."""

    def judge(self, concept: Concept) -> QualityAuditVerdict: ...

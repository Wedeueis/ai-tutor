from __future__ import annotations

from typing import Protocol

from pipeline.domain.agent import DraftConcept
from pipeline.domain.raw_material import RawItem


class ExtractionSkillPort(Protocol):
    """LLM-backed: turns one raw item into zero or more draft OKF concepts."""

    def extract(self, raw: RawItem) -> list[DraftConcept]: ...

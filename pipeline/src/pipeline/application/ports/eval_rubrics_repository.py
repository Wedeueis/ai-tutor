from __future__ import annotations

from typing import Protocol

from pipeline.domain.eval import Rubric


class EvalRubricsRepositoryPort(Protocol):
    """Loads the rubric list governing a domain's quality bar. Eval rubrics are
    dev-side validation data, not vault/knowledge-base content — see
    adapters/eval_rubrics/. Falls back to a base rubric list when the domain has
    none of its own yet (or there's no domain at all)."""

    def load_for_domain(self, domain_id: str | None) -> list[Rubric]: ...

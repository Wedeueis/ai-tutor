"""EvalRubricsRepositoryPort backed by plain JSON files under pipeline/evals/ —
dev-side quality validation, deliberately NOT vault/knowledge-base content. Each
file is ADK-Rubric-shaped, so it can be dropped into a real ADK .evalset.json
verbatim."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.domain.eval import Rubric, RubricContent

_BASE_FILENAME = "_base.json"


class JsonFileEvalRubricsRepository:
    def __init__(self, evals_dir: Path) -> None:
        self._evals_dir = evals_dir

    def load_for_domain(self, domain_id: str | None) -> list[Rubric]:
        if domain_id is not None:
            specific = self._read(f"{domain_id}.json")
            if specific is not None:
                return specific
        base = self._read(_BASE_FILENAME)
        return base or []

    def _read(self, relative_path: str) -> list[Rubric] | None:
        path = self._evals_dir / relative_path
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return [
            Rubric(
                rubric_id=entry["rubric_id"],
                rubric_content=RubricContent(
                    text_property=entry["rubric_content"]["text_property"]
                ),
                description=entry.get("description"),
                type=entry.get("type"),
            )
            for entry in raw
        ]

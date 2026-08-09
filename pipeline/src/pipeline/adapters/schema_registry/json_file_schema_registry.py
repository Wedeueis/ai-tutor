"""SchemaRegistryPort backed by JSON Schema files in pipeline/schemas/. Looks up
`<type>.schema.json` first; falls back to `_base.schema.json` (the always-valid
common fields from WIKI_SPEC.md §4.1) when no type-specific schema is registered."""

from __future__ import annotations

import json
from pathlib import Path

_BASE_SCHEMA_FILENAME = "_base.schema.json"


class JsonFileSchemaRegistry:
    def __init__(self, schemas_dir: Path) -> None:
        self._schemas_dir = schemas_dir

    def get_schema(self, concept_type: str) -> dict | None:
        specific = self._read(f"{concept_type}.schema.json")
        if specific is not None:
            return specific
        return self._read(_BASE_SCHEMA_FILENAME)

    def _read(self, filename: str) -> dict | None:
        path = self._schemas_dir / filename
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

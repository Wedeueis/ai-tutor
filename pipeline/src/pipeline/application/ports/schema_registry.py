from __future__ import annotations

from typing import Protocol


class SchemaRegistryPort(Protocol):
    """Looks up the JSON Schema for a concept `type`, if one has been registered."""

    def get_schema(self, concept_type: str) -> dict | None: ...

"""ConceptRepositoryPort backed by markdown+frontmatter files in the vault."""

from __future__ import annotations

from pathlib import Path

from pipeline.adapters.filesystem import frontmatter_codec, frontmatter_mapping
from pipeline.domain.concept import Concept, ConceptId

_RESERVED_FILENAMES = {"index.md", "log.md"}


class PathEscapesVaultError(ValueError):
    """A concept id resolved to a path outside the vault root."""


class MarkdownConceptRepository:
    def __init__(self, vault_root: Path) -> None:
        self._vault_root = vault_root.resolve()

    def _path_for(self, concept_id: ConceptId) -> Path:
        # Defense in depth alongside ConceptId's own validation: resolve
        # symlinks and `.`/`..` before checking containment, so a symlink
        # planted inside the vault (or one ConceptId's checks don't catch)
        # still can't read/write outside vault_root.
        path = (self._vault_root / f"{concept_id.value}.md").resolve()
        if path != self._vault_root and self._vault_root not in path.parents:
            raise PathEscapesVaultError(
                f"concept id {concept_id.value!r} resolves outside the vault root"
            )
        return path

    def load(self, concept_id: ConceptId) -> Concept:
        path = self._path_for(concept_id)
        data, body = frontmatter_codec.parse(path.read_text(encoding="utf-8"))
        return Concept(id=concept_id, frontmatter=frontmatter_mapping.from_yaml(data), body=body)

    def save(self, concept: Concept) -> None:
        path = self._path_for(concept.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = frontmatter_mapping.to_yaml(concept.frontmatter)
        path.write_text(frontmatter_codec.render(data, concept.body), encoding="utf-8")

    def list(self) -> list[ConceptId]:
        ids = []
        for path in self._vault_root.rglob("*.md"):
            if path.name in _RESERVED_FILENAMES:
                continue
            if any(part == "raw" for part in path.relative_to(self._vault_root).parts):
                continue
            relative = path.relative_to(self._vault_root).with_suffix("")
            ids.append(ConceptId(relative.as_posix()))
        return ids

    def exists(self, concept_id: ConceptId) -> bool:
        return self._path_for(concept_id).exists()

    def delete(self, concept_id: ConceptId) -> None:
        self._path_for(concept_id).unlink(missing_ok=True)

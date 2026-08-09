"""Local settings, overridable via env vars. The only place default paths/models
for the local stack (Ollama, ChromaDB, SQLite) are decided."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class Settings:
    vault_path: Path
    ollama_host: str
    ollama_chat_model: str
    ollama_embed_model: str
    ollama_vision_model: str
    chroma_dir: Path
    sqlite_path: Path
    schemas_dir: Path
    evals_dir: Path
    parsed_images_dir: Path

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = _PIPELINE_ROOT / ".data"
        return cls(
            vault_path=Path(
                os.environ.get("VAULT_PATH", str(_PIPELINE_ROOT.parent / "vault"))
            ).resolve(),
            ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            ollama_chat_model=os.environ.get("OLLAMA_CHAT_MODEL", "llama3.1:8b"),
            ollama_embed_model=os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            ollama_vision_model=os.environ.get("OLLAMA_VISION_MODEL", "llava"),
            chroma_dir=Path(os.environ.get("CHROMA_DIR", str(data_dir / "chroma"))),
            sqlite_path=Path(os.environ.get("SQLITE_PATH", str(data_dir / "metadata.db"))),
            schemas_dir=Path(os.environ.get("SCHEMAS_DIR", str(_PIPELINE_ROOT / "schemas"))),
            evals_dir=Path(os.environ.get("EVALS_DIR", str(_PIPELINE_ROOT / "evals"))),
            parsed_images_dir=Path(
                os.environ.get("PARSED_IMAGES_DIR", str(data_dir / "parsed-images"))
            ),
        )

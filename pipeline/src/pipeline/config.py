"""Local settings, overridable via env vars (or a `pipeline/.env` file — see
below). The only place default paths/models/tunables for the local stack
(Ollama, ChromaDB, SQLite, the MCP server) are decided; nothing else in this
codebase reads `os.environ` directly. If a value needs to be configurable,
it belongs here, not as a hardcoded default in an adapter or domain module.

On why this stays one flat `Settings` dataclass rather than a `ConfigManager`
with multiple profiles/contexts: there is currently exactly one runtime
shape — a single local process (CLI command or MCP server) that resolves its
configuration once at startup from the environment it was launched in. CLI
and the MCP server already get different values for the same settings simply
by being launched with different env vars (or a different `.env` file) — that
*is* per-context configuration, with no extra machinery. A manager/registry
layer (named profiles, hot-reload, per-request overrides) would be built for
a usage pattern that doesn't exist yet — e.g. one process serving multiple
tenants/vaults with different config at the same time. If that shows up,
that's the trigger to introduce one; building it now would be speculative.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent

# `override=False` (the default): real process env vars always win over the
# `.env` file, so `.env` only fills in what isn't already set — e.g. by a
# shell, a container's env, or a CI secret. Safe to call even if the file
# doesn't exist (a no-op).
load_dotenv(_PIPELINE_ROOT / ".env")


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw is not None else default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return float(raw) if raw is not None else default


@dataclass(frozen=True)
class Settings:
    vault_path: Path
    ollama_host: str
    ollama_chat_model: str
    ollama_embed_model: str
    ollama_vision_model: str
    ollama_timeout_seconds: float
    ollama_max_predict_tokens: int
    ollama_max_retries: int
    ollama_retry_backoff_seconds: float
    chroma_dir: Path
    sqlite_path: Path
    schemas_dir: Path
    evals_dir: Path
    parsed_images_dir: Path
    chunk_max_chars: int
    disambiguation_confidence_threshold: float
    eval_threshold: float
    log_level: str
    mcp_host: str
    mcp_port: int
    mcp_stateless: bool
    mcp_auth_token: str | None

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = _PIPELINE_ROOT / ".data"
        return cls(
            vault_path=Path(
                os.environ.get("VAULT_PATH", str(_PIPELINE_ROOT.parent / "vault"))
            ).resolve(),
            ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            ollama_chat_model=os.environ.get("OLLAMA_CHAT_MODEL", "llama3.1:8b"),
            ollama_embed_model=os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            ollama_vision_model=os.environ.get("OLLAMA_VISION_MODEL", "llava"),
            ollama_timeout_seconds=_float_env("OLLAMA_TIMEOUT_SECONDS", 300.0),
            ollama_max_predict_tokens=_int_env("OLLAMA_MAX_PREDICT_TOKENS", 2048),
            ollama_max_retries=_int_env("OLLAMA_MAX_RETRIES", 3),
            ollama_retry_backoff_seconds=_float_env("OLLAMA_RETRY_BACKOFF_SECONDS", 1.0),
            chroma_dir=Path(os.environ.get("CHROMA_DIR", str(data_dir / "chroma"))),
            sqlite_path=Path(os.environ.get("SQLITE_PATH", str(data_dir / "metadata.db"))),
            schemas_dir=Path(os.environ.get("SCHEMAS_DIR", str(_PIPELINE_ROOT / "schemas"))),
            evals_dir=Path(os.environ.get("EVALS_DIR", str(_PIPELINE_ROOT / "evals"))),
            parsed_images_dir=Path(
                os.environ.get("PARSED_IMAGES_DIR", str(data_dir / "parsed-images"))
            ),
            chunk_max_chars=_int_env("CHUNK_MAX_CHARS", 4000),
            disambiguation_confidence_threshold=_float_env(
                "DISAMBIGUATION_CONFIDENCE_THRESHOLD", 0.75
            ),
            eval_threshold=_float_env("EVAL_THRESHOLD", 0.7),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            mcp_host=os.environ.get("MCP_HOST", "127.0.0.1"),
            mcp_port=_int_env("MCP_PORT", 8000),
            mcp_stateless=_bool_env("MCP_STATELESS", True),
            mcp_auth_token=os.environ.get("MCP_AUTH_TOKEN") or None,
        )

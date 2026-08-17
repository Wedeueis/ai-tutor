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

import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv

from pipeline.adapters.openrouter.client import DEFAULT_BASE_URL

_PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent

# `override=False` (the default): real process env vars always win over the
# `.env` file, so `.env` only fills in what isn't already set — e.g. by a
# shell, a container's env, or a CI secret. Safe to call even if the file
# doesn't exist (a no-op).
load_dotenv(_PIPELINE_ROOT / ".env")


logger = logging.getLogger(__name__)


class ChatProvider(str, Enum):
    """Which service serves the LLM-backed skills.

    `OLLAMA` is the default and keeps everything on the machine. `OPENROUTER`
    reaches cloud models with better judgement (issue #19) at the cost of
    sending vault content — raw notes, concept bodies, whatever a skill puts in
    a prompt — to a third party. That is a deliberate, configured choice, never
    a default.

    Embeddings and vision are not affected either way: they stay local
    unconditionally. Every vector in ChromaDB was produced by one embedding
    model, so changing it invalidates the index rather than improving it."""

    OLLAMA = "ollama"
    OPENROUTER = "openrouter"

DEFAULT_OPENROUTER_CHAT_MODEL = "deepseek/deepseek-v4-flash-0731"

DEFAULT_EMBED_MODEL = "qwen3-embedding:0.6b"
"""**Not `nomic-embed-text`.** The vault takes material in English *and*
Portuguese, and nomic is English-centric: on MTEB-BR (a Brazilian-Portuguese
benchmark over 93 models) the Qwen3-Embedding family leads the open models,
while multilingual-leaderboard rank predicts Portuguese performance only
loosely (ρ≈0.75).

`0.6b` rather than `4b` for a hardware reason, not a quality one: ingest
alternates chat and embedding calls per chunk, and both models share one 8GB
GPU with the chat model. At ~640MB this stays resident alongside it; the 4B
would evict it on every alternation.

32k of context is the other half — it lifts the ceiling on chunk size, which
matters once source documents are books."""

DEFAULT_EMBED_QUERY_INSTRUCTION = (
    "Given a search query, retrieve relevant passages and concepts that answer it"
)
"""What a *query* is for. Qwen3-Embedding is instruction-aware and expects this
on the query side only.

Safe to edit at any time: the document side carries no instruction, so changing
this re-tunes retrieval without invalidating a single stored vector. Set it
empty to disable prefixing entirely, which is what a non-instruct model wants."""
"""Cost is a first-class constraint on this project — it is a personal vault,
and a full prerequisite backfill is hundreds of calls. A premium model is not
a default here, and a cheap model underperforming is a reason to fix the
harness (reasoning off, bigger token budget, tolerant JSON parsing) before it
is a reason to spend more.

No default is safe on judgement alone, though: tool-calling and rubric-scoring
reliability are per-model properties, verified by sampling, and a single
passing run proves nothing (PRD v3 NFR3). Measure with
`pipeline eval-prerequisites` before trusting whatever is set here."""


def _chat_provider_env() -> ChatProvider:
    raw = os.environ.get("CHAT_PROVIDER", ChatProvider.OLLAMA.value).strip().lower()
    try:
        return ChatProvider(raw)
    except ValueError:
        # Falling back to local would silently keep using the model the user
        # was trying to move off. A typo here should stop the run.
        valid = ", ".join(p.value for p in ChatProvider)
        raise ValueError(f"CHAT_PROVIDER must be one of: {valid} (got {raw!r})") from None


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
    chat_provider: ChatProvider
    openrouter_api_key: str | None
    openrouter_base_url: str
    openrouter_chat_model: str
    openrouter_relatedness_model: str
    openrouter_max_tokens: int
    openrouter_reasoning: bool
    ollama_host: str
    ollama_chat_model: str
    ollama_relatedness_model: str
    ollama_embed_model: str
    embed_query_instruction: str
    passage_context_chars: int
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
    relatedness_min_score: float
    category_confidence_threshold: float
    prerequisite_threshold: float
    prerequisite_candidate_k: int
    search_pool_k: int
    search_graph_seed_k: int
    search_graph_max_hops: int
    search_graph_decay: float
    search_graph_category_decay: float
    search_rrf_k: int
    search_structured_min_results: int
    log_level: str
    mcp_host: str
    mcp_port: int
    mcp_stateless: bool
    mcp_auth_token: str | None

    @property
    def chat_model(self) -> str:
        """The model every text skill runs on, resolved for the active
        provider — so a skill asks for "the chat model" and never for
        "the Ollama chat model"."""
        if self.chat_provider is ChatProvider.OPENROUTER:
            return self.openrouter_chat_model
        return self.ollama_chat_model

    @property
    def relatedness_model(self) -> str:
        """Relatedness has always been separately configurable; keeping that
        per provider avoids a switch silently changing which model judges it."""
        if self.chat_provider is ChatProvider.OPENROUTER:
            return self.openrouter_relatedness_model
        return self.ollama_relatedness_model

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = _PIPELINE_ROOT / ".data"
        chat_model = os.environ.get("OLLAMA_CHAT_MODEL", "llama3.1:8b")
        provider = _chat_provider_env()
        openrouter_model = os.environ.get(
            "OPENROUTER_CHAT_MODEL", DEFAULT_OPENROUTER_CHAT_MODEL
        )
        if provider is ChatProvider.OPENROUTER:
            logger.warning(
                "CHAT_PROVIDER=openrouter: prompts (raw notes, concept bodies) "
                "will be sent to OpenRouter. Embeddings stay local."
            )
        return cls(
            chat_provider=provider,
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY") or None,
            openrouter_base_url=os.environ.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL),
            openrouter_chat_model=openrouter_model,
            openrouter_relatedness_model=os.environ.get(
                "OPENROUTER_RELATEDNESS_MODEL", openrouter_model
            ),
            # Deliberately not sharing OLLAMA_MAX_PREDICT_TOKENS. That value
            # caps a local model that might never emit an EOS; here the budget
            # also has to cover a reasoning model's hidden tokens, and a
            # too-small one returns empty content rather than truncated JSON.
            openrouter_max_tokens=_int_env("OPENROUTER_MAX_TOKENS", 8192),
            # Off by default: skill prompts ask for scored JSON whose own
            # `rationale` fields are the only reasoning anything reads, so
            # chain-of-thought tokens are billed and discarded — and a model
            # that spends its budget thinking returns empty content.
            openrouter_reasoning=_bool_env("OPENROUTER_REASONING", False),
            vault_path=Path(
                os.environ.get("VAULT_PATH", str(_PIPELINE_ROOT.parent / "vault"))
            ).resolve(),
            ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            ollama_chat_model=chat_model,
            ollama_relatedness_model=os.environ.get("OLLAMA_RELATEDNESS_MODEL", chat_model),
            ollama_embed_model=os.environ.get(
                "OLLAMA_EMBED_MODEL", DEFAULT_EMBED_MODEL
            ),
            embed_query_instruction=os.environ.get(
                "EMBED_QUERY_INSTRUCTION", DEFAULT_EMBED_QUERY_INSTRUCTION
            ),
            passage_context_chars=_int_env("PASSAGE_CONTEXT_CHARS", 1200),
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
            relatedness_min_score=_float_env("RELATEDNESS_MIN_SCORE", 0.5),
            category_confidence_threshold=_float_env("CATEGORY_CONFIDENCE_THRESHOLD", 0.6),
            prerequisite_threshold=_float_env("PREREQUISITE_THRESHOLD", 0.7),
            prerequisite_candidate_k=_int_env("PREREQUISITE_CANDIDATE_K", 5),
            search_pool_k=_int_env("SEARCH_POOL_K", 20),
            search_graph_seed_k=_int_env("SEARCH_GRAPH_SEED_K", 5),
            search_graph_max_hops=_int_env("SEARCH_GRAPH_MAX_HOPS", 2),
            search_graph_decay=_float_env("SEARCH_GRAPH_DECAY", 0.5),
            search_graph_category_decay=_float_env("SEARCH_GRAPH_CATEGORY_DECAY", 0.85),
            search_rrf_k=_int_env("SEARCH_RRF_K", 60),
            search_structured_min_results=_int_env("SEARCH_STRUCTURED_MIN_RESULTS", 3),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            mcp_host=os.environ.get("MCP_HOST", "127.0.0.1"),
            mcp_port=_int_env("MCP_PORT", 8000),
            mcp_stateless=_bool_env("MCP_STATELESS", True),
            mcp_auth_token=os.environ.get("MCP_AUTH_TOKEN") or None,
        )

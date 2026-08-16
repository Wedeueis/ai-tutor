"""Environment-driven settings, mirroring `pipeline/src/pipeline/config.py`.

The point of this module is NFR1: keep the model provider behind a
configurable seam. Local-first is the default and the only supported setup
today; moving to a cloud provider with reliable tool calling is deferred
(issue #19) and must not require touching anything but this file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_TUTOR_ROOT = Path(__file__).resolve().parents[2]
_VAULT_ROOT = _TUTOR_ROOT.parent / "vault"
"""The sibling checkout's vault. A path, never an import: `tutor` reads the
vault's *content* only over MCP (rule 1). The one thing it touches on disk is
the inbox, which is not the bundle."""

DEFAULT_CHAT_MODEL = "qwen3.5:4b"
"""**Not `llama3.1:8b`** — NFR2. Measured in #12: 0/6 real tool calls once the
system prompt mentions tools, against 6/6 for `qwen3.5:4b` on the same probe.
It remains the default in both `agent/` and `pipeline`; `tutor` must not
inherit it, because every teaching turn is a tool-calling path.

Tool-calling reliability is a per-model property verified by *sampling*
(NFR3) — it is nondeterministic, and a single passing run proves nothing. Task
5.2 owns that verification; this constant only ensures the starting point is
not the model already known to fail."""


LOCAL_PROVIDER = "ollama_chat"
"""`ollama_chat/<model>`, not `ollama/<model>` — the latter has documented
tool-loop and context bugs in LiteLLM's Ollama integration, and every teaching
turn is a tool-calling path."""

KNOWN_BAD_TOOL_CALLERS = frozenset({"llama3.1:8b"})
"""Models measured to fail the tool-calling path outright (NFR2, #12): 0/6 real
calls once the system prompt mentions tools. Not a blocklist — configuring one
is the operator's call — but it is worth saying out loud, because the failure
looks like the model *narrating* tool calls in prose rather than erroring."""


@dataclass(frozen=True)
class Settings:
    ollama_host: str
    chat_model: str
    pipeline_mcp_url: str
    learner_db_path: Path
    session_db_url: str
    inquiries_dir: Path
    proposals_dir: Path

    @property
    def litellm_model(self) -> str:
        """The model string LiteLLM is given — the whole of NFR1's seam.

        A bare name (`qwen3.5:4b`) is local and gets the Ollama prefix; anything
        already naming a provider (`openrouter/deepseek/deepseek-chat`) is
        passed through untouched. That is what makes #19's swap a matter of
        setting one environment variable rather than editing code."""
        if "/" in self.chat_model:
            return self.chat_model
        return f"{LOCAL_PROVIDER}/{self.chat_model}"

    @property
    def model_api_base(self) -> str | None:
        """`ollama_host` for a local model, and nothing for a hosted one —
        pointing a hosted provider at localhost would fail in a confusing way."""
        if self.litellm_model.startswith(f"{LOCAL_PROVIDER}/"):
            return self.ollama_host
        return None

    @property
    def model_is_known_bad_at_tool_calling(self) -> bool:
        return self.chat_model in KNOWN_BAD_TOOL_CALLERS

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = Path(os.environ.get("TUTOR_DATA_DIR", str(_TUTOR_ROOT / ".data")))
        return cls(
            ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
            chat_model=os.environ.get("TUTOR_CHAT_MODEL", DEFAULT_CHAT_MODEL),
            pipeline_mcp_url=os.environ.get("PIPELINE_MCP_URL", "http://127.0.0.1:8000/mcp"),
            # Two SQLite files, deliberately. ADK is pre-1.0 and its session
            # schema will churn; the review history is the one thing here that
            # cannot be regenerated, so it does not live in the same file.
            learner_db_path=Path(
                os.environ.get("LEARNER_DB_PATH", str(data_dir / "learner.db"))
            ),
            session_db_url=os.environ.get(
                "TUTOR_SESSION_DB_URL", f"sqlite:///{data_dir / 'sessions.db'}"
            ),
            # The two directories `tutor` may write to, and the only ones.
            # `vault/raw/` is a capture surface, explicitly not part of the OKF
            # bundle — `tutor` never writes the bundle itself (#8).
            inquiries_dir=Path(
                os.environ.get(
                    "TUTOR_INQUIRIES_DIR", str(_VAULT_ROOT / "raw" / "inquiries")
                )
            ),
            # Not in the vault at all: a proposal is waiting for a human, and
            # approving it means moving the file into `vault/raw/`.
            proposals_dir=Path(
                os.environ.get("TUTOR_PROPOSALS_DIR", str(_TUTOR_ROOT / "proposals"))
            ),
        )

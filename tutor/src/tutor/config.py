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

DEFAULT_CHAT_MODEL = "qwen3.5:4b"
"""**Not `llama3.1:8b`** — NFR2. Measured in #12: 0/6 real tool calls once the
system prompt mentions tools, against 6/6 for `qwen3.5:4b` on the same probe.
It remains the default in both `agent/` and `pipeline`; `tutor` must not
inherit it, because every teaching turn is a tool-calling path.

Tool-calling reliability is a per-model property verified by *sampling*
(NFR3) — it is nondeterministic, and a single passing run proves nothing. Task
5.2 owns that verification; this constant only ensures the starting point is
not the model already known to fail."""


@dataclass(frozen=True)
class Settings:
    ollama_host: str
    chat_model: str
    pipeline_mcp_url: str
    learner_db_path: Path
    session_db_url: str

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
        )

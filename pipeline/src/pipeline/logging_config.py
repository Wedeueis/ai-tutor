"""The one place logging is configured. Every module gets its logger the
normal way (`logging.getLogger(__name__)`) and just logs — nothing else in
the codebase should call `logging.basicConfig` or add handlers itself.

Deliberately separate from CLI output: `typer.echo` in `cli/main.py` is the
user-facing result of a command (what got created, what matched a search).
This is the operational log — what the pipeline is *doing*, at a level of
detail useful for debugging a run after the fact — and is what the MCP
server relies on entirely, since it has no `typer.echo` equivalent."""

from __future__ import annotations

import logging

_CONFIGURED = False


def configure_logging(level: str = "INFO") -> None:
    """Idempotent — safe to call from every entry point (CLI, MCP server,
    tests) without double-configuring or clobbering a level set by an
    earlier call in the same process."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    _CONFIGURED = True

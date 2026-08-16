"""`ContributionPort` over two directories.

The only place in `tutor` that writes outside `learner.db`, and it can write to
exactly two places — one for inquiries, one for proposals — both fixed when it
is constructed. There is no method taking a destination.

**It never overwrites.** The inbox is somebody's capture surface; a second
inquiry about the same thing on the same day gets its own file rather than
replacing the first. Losing a note the user might have already started editing
would be a far worse failure than a duplicate.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from tutor.domain.contribution import Inquiry, Proposal

logger = logging.getLogger(__name__)

_MAX_COLLISIONS = 100


class OutsideTheAllowedRoots(RuntimeError):
    """A write resolved outside the directory it was meant for.

    Should be unreachable — `slugify` strips every path separator — which is
    exactly why it is checked. This adapter is the one component that can touch
    the user's vault, and "should be unreachable" is not a property worth
    trusting on the write path."""


class FilesystemContributions:
    def __init__(self, inquiries_dir: Path, proposals_dir: Path) -> None:
        self._inquiries_dir = inquiries_dir
        self._proposals_dir = proposals_dir

    def record_inquiry(self, inquiry: Inquiry) -> Path:
        on = _today()
        return self._write(
            self._inquiries_dir, inquiry.filename(on), inquiry.render(on)
        )

    def propose_concept(self, proposal: Proposal) -> Path:
        on = _today()
        return self._write(
            self._proposals_dir, proposal.filename(on), proposal.render(on)
        )

    def _write(self, directory: Path, filename: str, content: str) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = _contained(directory, filename)
        path = _unused(path)
        path.write_text(content, encoding="utf-8")
        logger.info("wrote %s", path)
        return path


if TYPE_CHECKING:  # pragma: no cover
    from tutor.application.ports.outbound.contributions import ContributionPort

    def _conforms_to_the_port(
        contributions: FilesystemContributions,
    ) -> ContributionPort:
        """Structural typing is only checked where a value crosses the seam,
        and nothing wires this adapter up yet. Until something does, this is
        what makes mypy notice if a signature here drifts from the port."""
        return contributions


def _contained(directory: Path, filename: str) -> Path:
    path = (directory / filename).resolve()
    root = directory.resolve()
    if root not in path.parents:
        raise OutsideTheAllowedRoots(f"{path} is not inside {root}")
    return path


def _unused(path: Path) -> Path:
    """`name.md`, then `name-2.md`, `name-3.md`. Never `name.md` twice."""
    if not path.exists():
        return path
    for suffix in range(2, _MAX_COLLISIONS + 1):
        candidate = path.with_name(f"{path.stem}-{suffix}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise OutsideTheAllowedRoots(
        f"{_MAX_COLLISIONS} files already named like {path.name} — refusing to keep going"
    )


def _today() -> date:
    """UTC, so a filename does not depend on which side of midnight the
    learner's timezone is on when the same session is replayed elsewhere."""
    return datetime.now(UTC).date()

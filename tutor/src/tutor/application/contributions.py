"""The pass that runs after a session ends.

Reads what was taught and what was said, asks a model what it revealed about
the **vault**, and files the answers through `ContributionPort` — the port
Task 5.3 built and nothing called.

Three properties this has to hold, in descending order of how badly it goes
wrong if it does not:

1. **It can never touch the review log.** A failure here loses inquiries, which
   is survivable; a failure that rolled back a review would lose the one thing
   in this system that cannot be regenerated. So it runs *after* every event is
   already committed, and it swallows its own exceptions.
2. **Nothing about the learner can be emitted.** Not by filtering — by there
   being no `Discovery` kind for it and no `ContributionPort` verb that takes
   one (§2.1, NFR5).
3. **It runs while the transcript is live.** ADK's session store is disposable
   (#39), so this is not a nightly job over old sessions; it is the last thing
   a session does.
"""

from __future__ import annotations

import logging
from pathlib import Path

from tutor.application.ports.outbound.contributions import ContributionPort
from tutor.application.ports.outbound.discovery import (
    Discovery,
    DiscoveryKind,
    DiscoverySkillPort,
    TranscriptPort,
)
from tutor.application.teaching import SessionReport
from tutor.domain.contribution import Inquiry, InquiryKind, Proposal

logger = logging.getLogger(__name__)

_INQUIRY_KINDS = {
    DiscoveryKind.COVERAGE_GAP: InquiryKind.COVERAGE_GAP,
    DiscoveryKind.CONTRADICTION: InquiryKind.CONTRADICTION,
}
"""Gaps and contradictions become inquiries and go straight to the inbox: they
create no knowledge, they ask for some. A derived concept is an answer, and
answers wait for a human (§2.1)."""


class ContributionPass:
    def __init__(
        self,
        transcripts: TranscriptPort,
        discoveries: DiscoverySkillPort,
        contributions: ContributionPort,
    ) -> None:
        self._transcripts = transcripts
        self._discoveries = discoveries
        self._contributions = contributions

    async def run(self, session_id: str, report: SessionReport) -> list[Path]:
        """Everything filed, or an empty list.

        **Never raises.** By the time this runs every review is already durably
        recorded, and a session must not end in a traceback because a model was
        unavailable to speculate about the vault. The failure is logged and the
        inquiries are lost, which is the right thing to lose (#39)."""
        if not report.concept_ids:
            return []

        try:
            transcript = await self._transcripts.read(session_id)
            discovered = await self._discoveries.discover(
                transcript, report.concept_ids
            )
        except Exception:  # noqa: BLE001 - see the docstring
            logger.exception("the contribution pass failed — no inquiries filed")
            return []

        written: list[Path] = []
        for discovery in discovered:
            try:
                written.append(self._file(discovery))
            except Exception:  # noqa: BLE001 - one bad discovery must not lose the rest
                logger.exception("could not file %r", discovery.title)
        return written

    def _file(self, discovery: Discovery) -> Path:
        """The only fork in this module, and it is exhaustive over
        `DiscoveryKind` — which is the point. A new kind cannot be added without
        deciding here where it goes, and there is no default branch that would
        quietly route an unfamiliar one into the vault."""
        if discovery.kind in _INQUIRY_KINDS:
            return self._contributions.record_inquiry(
                Inquiry(
                    kind=_INQUIRY_KINDS[discovery.kind],
                    title=discovery.title,
                    body=discovery.body,
                    concept_ids=discovery.concept_ids,
                )
            )
        return self._contributions.propose_concept(
            Proposal(
                title=discovery.title,
                body=discovery.body,
                concept_ids=discovery.concept_ids,
            )
        )

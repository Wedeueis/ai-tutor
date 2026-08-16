"""The only way anything leaves `tutor`.

Two verbs. That is the whole design: **the boundary is enforced by what this
protocol does not have**, not by a guard that inspects content and decides.

There is no `record_blindspot`, and there is no verb taking free text or a
destination path. A learner's blindspot — what they confuse, what they keep
getting wrong — is a reading of the review log, it is meaningless to anyone who
was not there, and it stays in `learner.db`. A later feature that wanted to
"just file a note about the learner" would have to add a method here to do it,
which is a change someone reviews, rather than passing a differently-worded
string to an existing one (NFR5).

Synchronous, unlike `VaultPort`: these are local file writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from tutor.domain.contribution import Inquiry, Proposal


class ContributionPort(Protocol):
    def record_inquiry(self, inquiry: Inquiry) -> Path:
        """A question about the vault → the inbox, **automatically**.

        No approval step, because an inquiry creates no knowledge: it asks for
        some. `vault/raw/inquiries/` keeps it visibly separate from material the
        user captured deliberately, and gives the research-and-synthesise flow
        a defined place to read from when it lands (#15)."""
        ...

    def propose_concept(self, proposal: Proposal) -> Path:
        """A derived concept → `tutor/proposals/`, **awaiting a human**.

        Deliberately not the inbox. `pipeline` remains the only thing that ever
        creates a concept, and approving a proposal is a person moving the file
        into `vault/raw/` (§2.1)."""
        ...

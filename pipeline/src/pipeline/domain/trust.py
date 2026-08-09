"""Trust tier derivation from `verified` (WIKI_SPEC.md §5.3)."""

from __future__ import annotations

from enum import Enum

from pipeline.domain.concept import VerificationEvent


class TrustTier(str, Enum):
    UNVERIFIED = "unverified"
    MACHINE_CONFIRMED = "machine-confirmed"
    HUMAN_REVIEWED = "human-reviewed"


def derive_trust_tier(verified: list[VerificationEvent]) -> TrustTier:
    """No `verified` => unverified. Any human verifier => human-reviewed. Otherwise
    (non-human verifiers only) => machine-confirmed (§5.3)."""
    if not verified:
        return TrustTier.UNVERIFIED
    if any(event.by.is_human for event in verified):
        return TrustTier.HUMAN_REVIEWED
    return TrustTier.MACHINE_CONFIRMED

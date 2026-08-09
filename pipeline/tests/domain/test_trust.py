from datetime import datetime

from pipeline.domain.concept import Actor, VerificationEvent
from pipeline.domain.trust import TrustTier, derive_trust_tier


def test_no_verified_is_unverified():
    assert derive_trust_tier([]) is TrustTier.UNVERIFIED


def test_process_only_is_machine_confirmed():
    events = [VerificationEvent(by=Actor("process:nightly"), at=datetime.now())]
    assert derive_trust_tier(events) is TrustTier.MACHINE_CONFIRMED


def test_any_human_is_human_reviewed():
    events = [
        VerificationEvent(by=Actor("process:nightly"), at=datetime.now()),
        VerificationEvent(by=Actor("human:ahormati"), at=datetime.now()),
    ]
    assert derive_trust_tier(events) is TrustTier.HUMAN_REVIEWED

"""How deep the learner intends to go in one Category.

Learner intent, so **episodic**: the vault never records what someone wants to
specialise in. Bound to a `type: Category` rather than a Domain — the
granularity that expresses "specialise in GraphRAG, stay aware of the rest of
ML" (PRD v3 RF3.3).

The stability threshold and evidence requirement each level defines land in
Task 2.2, together with `meets_target`. Thresholds are expressed in **days of
interval**, never a bare float, so the number means something a human can
argue with."""

from __future__ import annotations

from enum import Enum


class DepthLevel(str, Enum):
    AWARE = "aware"
    WORKING = "working"
    SPECIALIST = "specialist"


DEFAULT_DEPTH_LEVEL = DepthLevel.AWARE
"""What an untargeted Category resolves to.

Not a placeholder: new Categories arrive from ingest unseen, and defaulting to
anything deeper would commit the learner to study they never chose (PRD v3
RF3.3)."""

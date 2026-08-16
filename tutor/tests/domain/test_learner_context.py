"""The volatile tier — pure domain, no fakes, no I/O.

The tests that matter here are the negative ones. What this module *omits* is
the decision (#39); what it includes is comparatively easy to get right.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tutor.domain.depth import DepthLevel
from tutor.domain.learner_context import (
    FRAMING,
    LearnerContext,
    humanize_elapsed,
)
from tutor.domain.scheduling import Rating

NOW = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


def _seen(days_ago: int, rating: Rating, times: int = 1, **kwargs) -> LearnerContext:
    return LearnerContext(
        times_seen=times,
        last_reviewed_at=NOW - timedelta(days=days_ago),
        last_rating=rating,
        **kwargs,
    )


# --- what must never appear -----------------------------------------------

FORBIDDEN = ("stability", "difficulty", "retrievability", "due", "40.3", "fsrs")


@pytest.mark.parametrize(
    "context",
    [
        LearnerContext(),
        _seen(150, Rating.AGAIN, times=3),
        _seen(1, Rating.EASY, times=12, depth_target=DepthLevel.SPECIALIST),
    ],
)
def test_no_scheduler_number_ever_reaches_the_prompt(context):
    """The decision in #39. `stability = 40.3` is not a fact a model can use
    responsibly — it will be paraphrased, and the natural paraphrase is "you
    know this well", which is exactly what the invariant block forbids."""
    rendered = context.render(NOW).lower()

    for forbidden in FORBIDDEN:
        assert forbidden not in rendered


def test_the_rating_is_words_not_a_number():
    """The learner never sees a 1-4 scale and neither does the model: what
    matters for register is what the last attempt looked like."""
    rendered = _seen(30, Rating.AGAIN).render(NOW)

    assert "it had gone completely" in rendered
    assert "1" not in rendered.replace("2026", "")


def test_the_date_is_never_shown_as_a_date():
    """A date makes the model do arithmetic it is bad at, in a context where
    the answer sets the register of the whole conversation."""
    rendered = _seen(150, Rating.GOOD).render(NOW)

    assert "2026" not in rendered
    assert "about 5 months ago" in rendered


# --- what must appear -----------------------------------------------------


def test_the_framing_line_is_always_present():
    """Load-bearing: without it a model handed a history summarises it as an
    assessment, which is the failure the numbers would have caused, in prose."""
    assert FRAMING in LearnerContext().render(NOW)
    assert FRAMING in _seen(3, Rating.GOOD).render(NOW)


def test_a_first_meeting_says_there_is_no_history():
    """And says not to imply there is one — a model with an empty record will
    otherwise invent a plausible past."""
    rendered = LearnerContext().render(NOW)

    assert "first time" in rendered
    assert "do not imply there is" in rendered


def test_the_depth_target_is_stated_plainly():
    """Learner *intent*, not performance — which is why it is safe to state
    where the history is not."""
    rendered = _seen(3, Rating.GOOD, depth_target=DepthLevel.SPECIALIST).render(NOW)

    assert "specialist" in rendered
    assert "own words" in rendered  # the requirement's description


def test_meeting_it_once_reads_as_english():
    assert "met it once before" in _seen(3, Rating.GOOD, times=1).render(NOW)
    assert "met it 4 times" in _seen(3, Rating.GOOD, times=4).render(NOW)


def test_is_first_meeting():
    assert LearnerContext().is_first_meeting
    assert not _seen(1, Rating.GOOD).is_first_meeting


def test_a_history_with_no_rating_does_not_invent_one():
    context = LearnerContext(times_seen=2, last_reviewed_at=NOW - timedelta(days=5))

    assert "unclear how it went" in context.render(NOW)


# --- elapsed time ---------------------------------------------------------


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (0, "earlier today"),
        (1, "yesterday"),
        (3, "3 days ago"),
        (9, "about a week ago"),
        (21, "about 3 weeks ago"),
        (150, "about 5 months ago"),
        (400, "over a year ago"),
        (900, "more than 2 years ago"),
    ],
)
def test_elapsed_time_is_felt_duration(days, expected):
    assert humanize_elapsed(NOW - timedelta(days=days), NOW) == expected


def test_a_future_timestamp_does_not_produce_nonsense():
    """Clock skew, or a replayed log. "in -3 days" would be worse than
    imprecise — it would be the model's first hint that something is wrong."""
    assert humanize_elapsed(NOW + timedelta(days=3), NOW) == "just now"

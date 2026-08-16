"""What the tutor is told about the learner, and what it is never told.

The volatile tier of the prompt (RF2.7). Until now there was no such tier —
`compose()` returned soul + pedagogy + invariants, and the concept was used
only to *select* a pedagogy — so "frozen at session start" was vacuously true.
This is the thing it freezes.

**No FSRS number ever appears here.** Not stability, not difficulty, not
retrievability, not a due date. `stability = 40.3` is not a fact a model can
use responsibly: it will be paraphrased, and the natural paraphrase is "you
know this well", which is precisely the claim the invariant block forbids. A
number the model cannot interpret is a number it will interpret badly.

What it gets instead is the *qualitative* version — how long ago, and how it
went — which is what empathy actually needs. "It's been five months and it
slipped last time" is the difference between opening with "let's rebuild this
one" and opening with "quick check".

Pure domain: prose in, prose out, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tutor.domain.depth import DEFAULT_DEPTH_LEVEL, DepthLevel, requirement_for
from tutor.domain.scheduling import Rating

FRAMING = (
    "The notes above are a record of what happened, not a verdict on what the "
    "learner knows. You do not decide whether something is learned — the review "
    "log does, and it is not shown to you as a score. Use this to pitch the "
    "conversation: how long it has been, and how it went last time. Do not read "
    "it back to them, and do not turn it into a judgement about their progress."
)
"""Composed with the record, and load-bearing.

Without it the qualitative version drifts back into the failure the numbers
would have caused — a model handed a history will summarise it as an
assessment unless told plainly that summarising it is not its job."""

_RATING_PHRASE: dict[Rating, str] = {
    Rating.AGAIN: "it had gone completely",
    Rating.HARD: "it came back, but slowly and with gaps",
    Rating.GOOD: "they had it",
    Rating.EASY: "it came straight back, with nothing missing",
}
"""The rating in words. The learner never sees a 1–4 scale and neither does the
model: what matters for register is what the last attempt *looked like*."""


@dataclass(frozen=True)
class LearnerContext:
    """One concept's history, as the tutor is allowed to know it.

    Deliberately missing every field `SchedulerState` carries. This is not a
    view of the projection — it is a different, smaller thing, and the fields
    that are absent are absent on purpose."""

    times_seen: int = 0
    last_reviewed_at: datetime | None = None
    last_rating: Rating | None = None
    depth_target: DepthLevel = DEFAULT_DEPTH_LEVEL

    @property
    def is_first_meeting(self) -> bool:
        return self.times_seen == 0

    def render(self, now: datetime) -> str:
        return "\n".join(
            [
                "# What has happened with this concept",
                "",
                self._history(now),
                "",
                self._target(),
                "",
                FRAMING,
            ]
        )

    def _history(self, now: datetime) -> str:
        if self.is_first_meeting or self.last_reviewed_at is None:
            return (
                "This is the first time the learner has been asked about it. "
                "There is no history to go on — do not imply there is."
            )

        when = humanize_elapsed(self.last_reviewed_at, now)
        outcome = (
            _RATING_PHRASE[self.last_rating] if self.last_rating else "it is unclear how it went"
        )
        times = (
            "They have met it once before"
            if self.times_seen == 1
            else f"They have met it {self.times_seen} times"
        )
        return f"{times}. Last time was {when}, and {outcome}."

    def _target(self) -> str:
        """The learner's declared *intent*, not their performance — which is why
        it is safe to state plainly where the history is not."""
        requirement = requirement_for(self.depth_target)
        return (
            f"How deep they have chosen to go here: **{self.depth_target.value}** — "
            f"{requirement.description}"
        )


def humanize_elapsed(since: datetime, now: datetime) -> str:
    """"five months ago", never `2026-03-04`.

    A date makes the model do arithmetic it is bad at, in a context where the
    answer changes the register of the whole conversation. Felt duration is the
    thing being communicated, so it is the thing that gets written down."""
    days = (now - since).days
    if days < 0:
        return "just now"
    if days == 0:
        return "earlier today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    if days < 14:
        return "about a week ago"
    if days < 60:
        return f"about {round(days / 7)} weeks ago"
    if days < 365:
        return f"about {round(days / 30)} months ago"
    if days < 730:
        return "over a year ago"
    return f"more than {days // 365} years ago"

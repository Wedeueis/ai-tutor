"""`LearnerStorePort` over `learner.db`.

The shape of this adapter follows from one decision: the review log is
authoritative and everything else is a cache. So `append_review` writes an
event and nothing else; `scheduler_state` brings the projection up to date on
read; and `replay` throws the cache away and rebuilds it from the log.

The scheduling algorithm is **injected**, not imported. This module owns
persistence and the replay loop; how a rating advances a `SchedulerState` is
`domain/scheduling.py`'s job (Task 2.1). Keeping it a parameter also makes the
checkpoint-invalidation rule testable without an FSRS implementation, and makes
`(algorithm, parameters)` something the caller declares rather than something
this file hardcodes."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from tutor.adapters.sqlite._thread_local_connection import ThreadLocalSqliteConnection
from tutor.domain.depth import DEFAULT_DEPTH_LEVEL, DepthLevel
from tutor.domain.review import ReviewEvent
from tutor.domain.scheduling import Rating, SchedulerState, State

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

Scheduler = Callable[[SchedulerState, Rating, datetime], SchedulerState]
"""`calculate_next_review`. `reviewed_at` is required, not optional: elapsed
time drives the stability update, so a two-argument scheduler cannot work."""


class SqliteLearnerStore:
    def __init__(
        self,
        db_path: Path,
        scheduler: Scheduler,
        algorithm: str,
        parameters: str,
    ) -> None:
        self._pool = ThreadLocalSqliteConnection(db_path, _SCHEMA_PATH)
        self._scheduler = scheduler
        self._algorithm = algorithm
        self._parameters = parameters

    @property
    def _connection(self) -> sqlite3.Connection:
        return self._pool.get()

    def close(self) -> None:
        self._pool.close()

    # --- the log ---------------------------------------------------------

    def append_review(self, event: ReviewEvent) -> None:
        """Append-only. There is no update or delete here, and the database
        refuses them too (see schema.sql's triggers).

        Deliberately does **not** advance the projection. A write that also
        maintained a cache would make the two able to disagree; instead the
        cache is brought up to date on read, from the log."""
        self._connection.execute(
            """
            INSERT INTO review_events (
                concept_id, rating, reviewed_at, algorithm, parameters,
                question, rubric, answer, grade, discursive
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.concept_id,
                int(event.rating),
                event.reviewed_at.isoformat(),
                event.algorithm,
                event.parameters,
                event.question,
                event.rubric,
                event.answer,
                event.grade,
                int(event.discursive),
            ),
        )
        self._connection.commit()

    def events(self, concept_id: str | None = None) -> list[ReviewEvent]:
        """The log itself, oldest first. Not on the port — the port is about
        projections — but the log is the thing worth reading directly when a
        projection looks wrong."""
        if concept_id is None:
            rows = self._connection.execute(
                "SELECT * FROM review_events ORDER BY id"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT * FROM review_events WHERE concept_id = ? ORDER BY id",
                (concept_id,),
            ).fetchall()
        return [_as_event(row) for row in rows]

    def has_discursive_evidence(self, concept_id: str) -> bool:
        """Read off the log, not off a projection: it is a fact about what
        happened, and no FSRS state carries it (RF4.4). `LIMIT 1` because the
        question is whether one such review exists, not how many."""
        row = self._connection.execute(
            "SELECT 1 FROM review_events WHERE concept_id = ? AND discursive = 1 LIMIT 1",
            (concept_id,),
        ).fetchone()
        return row is not None

    # --- projections -----------------------------------------------------

    def scheduler_state(self, concept_id: str) -> SchedulerState | None:
        """Brings the projection up to date, then returns it. None means the
        concept has never been reviewed — not that the cache is cold."""
        self._advance(concept_id)
        row = self._connection.execute(
            "SELECT * FROM scheduler_state WHERE concept_id = ?", (concept_id,)
        ).fetchone()
        return _as_scheduler_state(row) if row is not None else None

    def replay(self, concept_id: str | None = None) -> None:
        """Discards the cached projection and rebuilds it from the first event.

        Off the read path and cheap: a heavy decade is ~730k events (~35 MB), a
        full rebuild is seconds, one concept is milliseconds."""
        for target in [concept_id] if concept_id is not None else self._reviewed_concepts():
            self._rebuild(target, since_event_id=0, state=SchedulerState())

    def _advance(self, concept_id: str) -> None:
        """Applies whatever has happened since the last valid checkpoint.

        **A checkpoint is valid only for the exact `(algorithm, parameters)`
        that produced it.** A mismatch means the cached state was computed by
        scheduling that is no longer in force, so it is discarded and the
        concept replayed from its first event. Reusing it would silently
        corrupt every subsequent interval — the failure is invisible, which is
        why the identity lives on the row and is compared here rather than
        being cleared by hand after a re-fit."""
        checkpoint = self._connection.execute(
            "SELECT * FROM checkpoints WHERE concept_id = ?", (concept_id,)
        ).fetchone()

        if checkpoint is None:
            self._rebuild(concept_id, since_event_id=0, state=SchedulerState())
            return

        if (
            checkpoint["algorithm"] != self._algorithm
            or checkpoint["parameters"] != self._parameters
        ):
            self._rebuild(concept_id, since_event_id=0, state=SchedulerState())
            return

        row = self._connection.execute(
            "SELECT * FROM scheduler_state WHERE concept_id = ?", (concept_id,)
        ).fetchone()
        state = _as_scheduler_state(row) if row is not None else SchedulerState()
        self._rebuild(concept_id, since_event_id=checkpoint["last_event_id"], state=state)

    def _rebuild(self, concept_id: str, since_event_id: int, state: SchedulerState) -> None:
        rows = self._connection.execute(
            "SELECT * FROM review_events WHERE concept_id = ? AND id > ? ORDER BY id",
            (concept_id, since_event_id),
        ).fetchall()
        if not rows and since_event_id > 0:
            return  # already current

        last_event_id = since_event_id
        for row in rows:
            event = _as_event(row)
            state = self._scheduler(state, event.rating, event.reviewed_at)
            last_event_id = row["id"]

        if last_event_id == 0:
            return  # never reviewed: no projection to write

        self._write_projection(concept_id, state, last_event_id)

    def _write_projection(
        self, concept_id: str, state: SchedulerState, last_event_id: int
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO scheduler_state (
                concept_id, stability, difficulty, due, last_review, state, step
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(concept_id) DO UPDATE SET
                stability = excluded.stability,
                difficulty = excluded.difficulty,
                due = excluded.due,
                last_review = excluded.last_review,
                state = excluded.state,
                step = excluded.step
            """,
            (
                concept_id,
                state.stability,
                state.difficulty,
                state.due.isoformat() if state.due else None,
                state.last_review.isoformat() if state.last_review else None,
                int(state.state),
                state.step,
            ),
        )
        self._connection.execute(
            """
            INSERT INTO checkpoints (concept_id, last_event_id, algorithm, parameters)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(concept_id) DO UPDATE SET
                last_event_id = excluded.last_event_id,
                algorithm = excluded.algorithm,
                parameters = excluded.parameters
            """,
            (concept_id, last_event_id, self._algorithm, self._parameters),
        )
        self._connection.commit()

    def _reviewed_concepts(self) -> list[str]:
        return [
            row["concept_id"]
            for row in self._connection.execute(
                "SELECT DISTINCT concept_id FROM review_events ORDER BY concept_id"
            )
        ]

    # --- depth targets ---------------------------------------------------

    def depth_target(self, category_id: str) -> DepthLevel:
        """An unknown Category resolves to `aware` rather than raising. New
        Categories arrive from ingest unseen, and defaulting to depth would
        commit the learner to study they never chose."""
        row = self._connection.execute(
            "SELECT level FROM depth_targets WHERE category_id = ?", (category_id,)
        ).fetchone()
        if row is None:
            return DEFAULT_DEPTH_LEVEL
        try:
            return DepthLevel(row["level"])
        except ValueError:
            # A level written by a future version, or by hand. Falling back is
            # safer than raising: an unreadable target must not make the whole
            # study plan unbuildable.
            return DEFAULT_DEPTH_LEVEL

    def depth_targets(self) -> dict[str, DepthLevel]:
        """Every target the learner actually declared.

        Not on the port, for the same reason `events` is not: the port is about
        answering "what is the target for this Category", and it answers `aware`
        for a Category nobody ever touched. This distinguishes the two, which is
        what "show me my targets" needs — a learner has to be able to tell "I
        chose aware" from "nobody ever set this" (#20)."""
        return {
            row["category_id"]: DepthLevel(row["level"])
            for row in self._connection.execute(
                "SELECT category_id, level FROM depth_targets ORDER BY category_id"
            )
            if row["level"] in {level.value for level in DepthLevel}
        }

    def set_depth_target(self, category_id: str, level: DepthLevel) -> None:
        self._connection.execute(
            """
            INSERT INTO depth_targets (category_id, level) VALUES (?, ?)
            ON CONFLICT(category_id) DO UPDATE SET level = excluded.level
            """,
            (category_id, level.value),
        )
        self._connection.commit()


if TYPE_CHECKING:  # pragma: no cover
    from tutor.application.ports.outbound.learner_store import LearnerStorePort

    def _conforms_to_the_port(store: SqliteLearnerStore) -> LearnerStorePort:
        """Structural typing is only checked where a value actually crosses the
        seam, and nothing wires this store up yet. Until something does, this
        is what makes mypy notice if a signature here drifts from the port."""
        return store


def _as_event(row: sqlite3.Row) -> ReviewEvent:
    return ReviewEvent(
        concept_id=row["concept_id"],
        rating=Rating(row["rating"]),
        reviewed_at=datetime.fromisoformat(row["reviewed_at"]),
        algorithm=row["algorithm"],
        parameters=row["parameters"],
        question=row["question"],
        rubric=row["rubric"],
        answer=row["answer"],
        grade=row["grade"],
        discursive=bool(row["discursive"]),
    )


def _as_scheduler_state(row: sqlite3.Row) -> SchedulerState:
    return SchedulerState(
        stability=row["stability"],
        difficulty=row["difficulty"],
        due=datetime.fromisoformat(row["due"]) if row["due"] else None,
        last_review=(
            datetime.fromisoformat(row["last_review"]) if row["last_review"] else None
        ),
        state=State(row["state"]),
        step=row["step"],
    )

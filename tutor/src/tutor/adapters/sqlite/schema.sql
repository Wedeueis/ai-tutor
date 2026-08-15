-- learner.db — episodic memory. Owned entirely by `tutor`, shared with
-- nothing: not `pipeline`, and not ADK's session database.
--
-- One table here is authoritative and irreplaceable (`review_events`); one is
-- authoritative and small (`depth_targets`); the rest are caches that can be
-- thrown away and rebuilt.

-- The single source of truth. Append-only: see the triggers below.
CREATE TABLE IF NOT EXISTS review_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    concept_id   TEXT    NOT NULL,
    rating       INTEGER NOT NULL,  -- FSRS 1-4, stored raw so a replay does
                                    -- not depend on our enum still existing
    reviewed_at  TEXT    NOT NULL,  -- ISO-8601; elapsed time drives FSRS
    algorithm    TEXT    NOT NULL,  -- scheduling identity in force at the time
    parameters   TEXT    NOT NULL,

    -- The full exchange, as text rather than as pointers. A row has to stay
    -- independently interpretable years from now, after the concept has been
    -- rewritten and the rubric file has moved or been deleted.
    question     TEXT    NOT NULL,
    rubric       TEXT    NOT NULL,
    answer       TEXT    NOT NULL,
    grade        TEXT    NOT NULL,
    discursive   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_review_events_concept ON review_events (concept_id, id);

-- Append-only, enforced by the database rather than by the absence of a
-- method. The store exposes no update or delete path, but the log is the one
-- thing here that cannot be regenerated, so a stray `UPDATE` from a migration
-- script or a sqlite3 prompt should fail loudly too.
CREATE TRIGGER IF NOT EXISTS review_events_are_immutable
BEFORE UPDATE ON review_events
BEGIN
    SELECT RAISE(ABORT, 'review_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS review_events_are_not_deletable
BEFORE DELETE ON review_events
BEGIN
    SELECT RAISE(ABORT, 'review_events is append-only');
END;

-- Learner-declared intent. The only authoritative state here that is not an
-- event, and the only thing that cannot be rebuilt by replay — it records what
-- someone wants, not what happened.
CREATE TABLE IF NOT EXISTS depth_targets (
    category_id TEXT PRIMARY KEY,
    level       TEXT NOT NULL
);

-- Projection. Keyed by concept, not by card: assessments are ephemeral and
-- regenerated per review, so there is no card identity to key on.
CREATE TABLE IF NOT EXISTS scheduler_state (
    concept_id  TEXT PRIMARY KEY,
    stability   REAL,
    difficulty  REAL,
    due         TEXT,
    last_review TEXT,
    state       INTEGER NOT NULL,
    step        INTEGER NOT NULL
);

-- How far the projection has been advanced, and under what scheduling identity.
--
-- `algorithm` and `parameters` are not bookkeeping: a checkpoint is valid ONLY
-- for the exact pair that produced it. They live on the row so validity is
-- checked before use, rather than maintained by remembering to clear a table
-- after a parameter re-fit. Stale reuse silently corrupts scheduling.
CREATE TABLE IF NOT EXISTS checkpoints (
    concept_id    TEXT PRIMARY KEY,
    last_event_id INTEGER NOT NULL,
    algorithm     TEXT    NOT NULL,
    parameters    TEXT    NOT NULL
);

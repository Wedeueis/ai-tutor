"""Composition root: the only place `tutor`'s concrete adapters — the SQLite
learner store and the MCP vault client — get wired to the application's ports.

The commands here are thin on purpose. `review` and `teach` run a session and
own no logic beyond building the adapters — the loop lives in
`application/teaching.py`, which is what keeps it testable without ADK. `plan`
and `session` print what those two will consume, because a projection nobody
can look at is very hard to trust. `depth set` exists because RF3.3 is explicit
that depth targets need "a CLI or conversational way to set one, or the feature
is unusable": `set_depth_target` had existed since Task 1.2 with nothing able to
call it.

**`review` is the primary loop, not `teach`.** "Keep what I know from rotting"
is the request a spaced-repetition system exists to serve; "take me toward X"
is the one that needs the graph. They are separate commands because one serving
both would compromise both (#39).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

import typer

from tutor.adapters.adk.turn import AdkTeachingTurn
from tutor.adapters.llm.assessment import LiteLlmAssessmentSkill
from tutor.adapters.mcp.vault import McpVault
from tutor.adapters.sqlite.learner_store import SqliteLearnerStore
from tutor.agent import build_session_service
from tutor.application.review import ConductReview
from tutor.application.session import DEFAULT_SESSION_SIZE, Session, compose_session
from tutor.application.study_plan import (
    DEFAULT_MAX_HOPS,
    PlanItem,
    StudyPlan,
    StudyPlanner,
)
from tutor.application.teaching import (
    DEFAULT_VISIT_CAP,
    SessionReport,
    TeachSession,
    due_seed,
)
from tutor.config import Settings
from tutor.domain.depth import DepthLevel, requirement_for
from tutor.domain.scheduling import ALGORITHM, PARAMETERS_ID, calculate_next_review

app = typer.Typer(help="The stateful AI Tutor over the OKF vault.")
depth_app = typer.Typer(help="How deep to go in a Category, and what that asks for.")
app.add_typer(depth_app, name="depth")


@dataclass
class Container:
    settings: Settings
    learner_store: SqliteLearnerStore

    def vault(self) -> McpVault:
        return McpVault(self.settings.pipeline_mcp_url)


def _container() -> Container:
    settings = Settings.from_env()
    settings.learner_db_path.parent.mkdir(parents=True, exist_ok=True)
    return Container(
        settings=settings,
        learner_store=SqliteLearnerStore(
            settings.learner_db_path,
            # The scheduling identity is declared here, by the composition
            # root, rather than hardcoded in the store — a checkpoint is valid
            # only for the exact pair that produced it, so the pair has to be
            # something a caller states.
            scheduler=calculate_next_review,
            algorithm=ALGORITHM,
            parameters=PARAMETERS_ID,
        ),
    )


# --- depth targets --------------------------------------------------------


@depth_app.command("set")
def depth_set(category_id: str, level: DepthLevel) -> None:
    """Declare how deep to go in one Category.

    The Category is a vault concept id (`categories/graph-rag`); it is not
    validated against the vault on purpose, so a target can be set for a
    Category that ingest has not produced yet. A target for a Category that
    never appears is inert, not an error."""
    container = _container()
    container.learner_store.set_depth_target(category_id, level)
    requirement = requirement_for(level)
    typer.echo(f"{category_id}: {level.value}")
    typer.echo(f"  {requirement.description}")
    typer.echo(f"  threshold: {requirement.stability_days:g} days of stability")
    if requirement.requires_discursive:
        typer.echo("  evidence: needs a graded free-text answer, not just recall")


@depth_app.command("show")
def depth_show(category_id: str | None = typer.Argument(default=None)) -> None:
    """Show one Category's target, or every target that was actually declared.

    An untargeted Category answers `aware` — and it says so, because a learner
    has to be able to tell "I chose aware" from "nobody ever set this" (#20)."""
    container = _container()
    declared = container.learner_store.depth_targets()

    if category_id is not None:
        level = container.learner_store.depth_target(category_id)
        origin = "declared" if category_id in declared else "default, never set"
        typer.echo(f"{category_id}: {level.value}  ({origin})")
        return

    if not declared:
        typer.echo("No depth targets set. Every Category defaults to `aware`.")
        return
    for category, level in declared.items():
        typer.echo(f"{category}: {level.value}")


# --- the plan -------------------------------------------------------------


@app.command()
def plan(concept_id: str, max_hops: int = DEFAULT_MAX_HOPS) -> None:
    """Print the study plan for a goal concept.

    Nothing is stored: this recomputes from the prerequisite graph, the review
    log and the depth targets every time it runs (RF3.1)."""
    projection = asyncio.run(_plan(concept_id, max_hops))
    if not projection:
        typer.echo(f"Nothing to study for {concept_id} — everything is at target.")
        return
    for item in projection:
        typer.echo(_line(item))


@app.command()
def session(
    concept_id: str,
    size: int = DEFAULT_SESSION_SIZE,
    max_hops: int = DEFAULT_MAX_HOPS,
) -> None:
    """Print one session's worth of work: due-and-under-target first, then the
    rest of the under-target work, then new ground (RF3.4)."""
    now = datetime.now(UTC)
    composed: Session = compose_session(
        asyncio.run(_plan(concept_id, max_hops)), size=size, now=now
    )
    if not composed:
        typer.echo(f"Nothing to study for {concept_id} right now.")
        return
    for item in composed:
        typer.echo(_line(item, now=now))


@app.command()
def review(size: int = DEFAULT_SESSION_SIZE, cap: int = DEFAULT_VISIT_CAP) -> None:
    """Review everything that is due — the primary loop.

    No goal and no graph walk: every concept here has been studied before, so
    prerequisite ordering has nothing to contribute (#39)."""
    asyncio.run(_run_session(_due_seed(size), size=size, cap=cap))


@app.command()
def teach(
    concept_id: str,
    size: int = DEFAULT_SESSION_SIZE,
    cap: int = DEFAULT_VISIT_CAP,
    max_hops: int = DEFAULT_MAX_HOPS,
) -> None:
    """Work toward a concept: prerequisites first, then the concept itself."""
    asyncio.run(
        _run_session(_plan_seed(concept_id, size, max_hops), size=size, cap=cap)
    )


async def _due_seed(size: int) -> list[str]:
    return await due_seed(_container().learner_store, limit=size)


async def _plan_seed(concept_id: str, size: int, max_hops: int) -> list[str]:
    projection = await _plan(concept_id, max_hops)
    return [item.concept_id for item in compose_session(projection, size=size)]


async def _run_session(seed_awaitable, *, size: int, cap: int) -> None:
    """Composition root for a session: every adapter is built here and nowhere
    else, which is what keeps `application/teaching.py` free of ADK."""
    seed = await seed_awaitable
    if not seed:
        typer.echo("Nothing to study right now.")
        return

    container = _container()
    vault = container.vault()
    turns = AdkTeachingTurn(
        session_service=build_session_service(container.settings),
        session_id=f"tutor-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}",
        settings=container.settings,
    )
    assessments = LiteLlmAssessmentSkill(
        container.settings.litellm_model, container.settings.model_api_base
    )
    session = TeachSession(
        vault,
        container.learner_store,
        ConductReview(vault, container.learner_store, assessments),
        turns,
        visit_cap=cap,
    )

    typer.echo(f"{len(seed)} concept(s) this session. `/skip` to pass, `/quit` to stop.\n")
    try:
        report = await session.run(seed)
    finally:
        await vault.aclose()
    _report(report)


def _report(report: SessionReport) -> None:
    """Printed, never stored. There is no `sessions` table — every review was
    committed as it happened (#39)."""
    typer.echo("")
    if report.abandoned:
        typer.echo("Stopped early. Everything answered before that is recorded.")
    typer.echo(f"reviewed  {len(report.reviewed)}")
    if report.skipped:
        typer.echo(f"skipped   {', '.join(report.skipped)}")
    if report.ungraded:
        typer.echo(f"ungraded  {', '.join(report.ungraded)} (grader failed; nothing recorded)")


async def _plan(concept_id: str, max_hops: int) -> StudyPlan:
    container = _container()
    vault = container.vault()
    try:
        return await StudyPlanner(
            vault, container.learner_store, max_hops=max_hops
        ).plan(concept_id)
    finally:
        await vault.aclose()


def _line(item: PlanItem, now: datetime | None = None) -> str:
    marks = [item.kind.value, item.target.value]
    if item.due is not None:
        overdue = now is not None and item.due <= now
        marks.append(f"due {item.due.date().isoformat()}{' (overdue)' if overdue else ''}")
    if item.blocked:
        marks.append(f"blocked by {', '.join(item.unmet_prerequisites)}")
    return f"{item.concept_id}  [{'; '.join(marks)}]"


if __name__ == "__main__":  # pragma: no cover
    app()

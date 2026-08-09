"""Maps between the parsed YAML dict and the domain `Frontmatter` dataclass."""

from __future__ import annotations

from datetime import date, datetime

from pipeline.domain.concept import Actor, Frontmatter, Generated, Source, VerificationEvent
from pipeline.domain.eval import EvalResult, RubricScore

_KNOWN_KEYS = {
    "type",
    "title",
    "description",
    "resource",
    "tags",
    "sources",
    "generated",
    "verified",
    "status",
    "stale_after",
    "domain",
    "eval",
}


def _as_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return datetime.fromisoformat(str(value))


def _verified_list(raw) -> list[VerificationEvent]:
    if raw is None:
        return []
    entries = raw if isinstance(raw, list) else [raw]  # bare mapping => one-element list (§5.2)
    return [
        VerificationEvent(by=Actor(entry["by"]), at=_as_datetime(entry.get("at")))
        for entry in entries
    ]


def _sources_list(raw) -> list[Source]:
    if not raw:
        return []
    return [
        Source(
            resource=entry["resource"],
            id=entry.get("id"),
            title=entry.get("title"),
            author=entry.get("author"),
            usage_count=entry.get("usage_count"),
            last_modified=entry.get("last_modified"),
        )
        for entry in raw
    ]


def _eval_result(raw) -> EvalResult | None:
    if not raw:
        return None
    scores = [
        RubricScore(
            rubric_id=entry["rubric_id"],
            score=entry.get("score"),
            rationale=entry.get("rationale"),
        )
        for entry in raw.get("scores") or []
    ]
    return EvalResult(
        scores=scores,
        average_score=raw.get("average_score", 0.0),
        passed=bool(raw.get("passed", False)),
    )


def from_yaml(data: dict) -> Frontmatter:
    generated_raw = data.get("generated")
    generated = (
        Generated(by=Actor(generated_raw["by"]), at=_as_datetime(generated_raw.get("at")))
        if generated_raw
        else None
    )

    return Frontmatter(
        type=data["type"],
        title=data.get("title"),
        description=data.get("description"),
        resource=data.get("resource"),
        tags=list(data.get("tags") or []),
        sources=_sources_list(data.get("sources")),
        generated=generated,
        verified=_verified_list(data.get("verified")),
        status=data.get("status"),
        stale_after=(
            str(data["stale_after"]) if data.get("stale_after") is not None else None
        ),
        domain=data.get("domain"),
        eval=_eval_result(data.get("eval")),
        extra={k: v for k, v in data.items() if k not in _KNOWN_KEYS},
    )


def to_yaml(frontmatter: Frontmatter) -> dict:
    data: dict = {"type": frontmatter.type}
    if frontmatter.title is not None:
        data["title"] = frontmatter.title
    if frontmatter.description is not None:
        data["description"] = frontmatter.description
    if frontmatter.resource is not None:
        data["resource"] = frontmatter.resource
    if frontmatter.tags:
        data["tags"] = list(frontmatter.tags)
    if frontmatter.sources:
        data["sources"] = [
            {k: v for k, v in vars(source).items() if v is not None}
            for source in frontmatter.sources
        ]
    if frontmatter.generated is not None:
        entry = {"by": str(frontmatter.generated.by)}
        if frontmatter.generated.at is not None:
            entry["at"] = frontmatter.generated.at.isoformat()
        data["generated"] = entry
    if frontmatter.verified:
        data["verified"] = [
            {"by": str(event.by), "at": event.at.isoformat() if event.at else None}
            for event in frontmatter.verified
        ]
    if frontmatter.status is not None:
        data["status"] = frontmatter.status
    if frontmatter.stale_after is not None:
        data["stale_after"] = frontmatter.stale_after
    if frontmatter.domain is not None:
        data["domain"] = frontmatter.domain
    if frontmatter.eval is not None:
        data["eval"] = {
            "passed": frontmatter.eval.passed,
            "average_score": frontmatter.eval.average_score,
            "scores": [
                {"rubric_id": s.rubric_id, "score": s.score, "rationale": s.rationale}
                for s in frontmatter.eval.scores
            ],
        }
    data.update(frontmatter.extra)
    return data

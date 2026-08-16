"""Composition root: the only place concrete local adapters (Ollama, ChromaDB,
SQLite, filesystem) get wired to the application's ports."""

from __future__ import annotations

import json
from datetime import date

import typer

from pipeline.adapters.chroma.chroma_vector_search import ChromaVectorSearch
from pipeline.adapters.docling.document_parser import DoclingDocumentParser
from pipeline.adapters.eval_rubrics.json_file_eval_rubrics_repository import (
    JsonFileEvalRubricsRepository,
)
from pipeline.adapters.filesystem.filesystem_scanner import FilesystemScanner
from pipeline.adapters.filesystem.markdown_concept_repository import MarkdownConceptRepository
from pipeline.adapters.filesystem.raw_material_repository import FilesystemRawMaterialRepository
from pipeline.adapters.llm_skills.category_classification import (
    CategoryClassificationSkill,
)
from pipeline.adapters.llm_skills.domain_classification import (
    DomainClassificationSkill,
)
from pipeline.adapters.llm_skills.entity_disambiguation import (
    EntityDisambiguationSkill,
)
from pipeline.adapters.llm_skills.extraction import ExtractionSkill
from pipeline.adapters.llm_skills.prerequisite_judgement import (
    PrerequisiteJudgementSkill,
)
from pipeline.adapters.llm_skills.quality_audit import QualityAuditSkill
from pipeline.adapters.llm_skills.quality_eval import QualityEvalSkill
from pipeline.adapters.llm_skills.relatedness import RelatednessSkill
from pipeline.adapters.llm_skills.type_classification import (
    TypeClassificationSkill,
)
from pipeline.adapters.ollama.client import OllamaClient
from pipeline.adapters.ollama.embedding import OllamaEmbedding
from pipeline.adapters.ollama.skills.image_captioning import OllamaImageCaptioningSkill
from pipeline.adapters.openrouter.client import OpenRouterClient
from pipeline.adapters.schema_registry.json_file_schema_registry import (
    JsonFileSchemaRegistry,
)
from pipeline.adapters.sqlite.sqlite_bundle_log import SqliteBundleLog
from pipeline.adapters.sqlite.sqlite_intake_repository import SqliteIntakeRepository
from pipeline.adapters.sqlite.sqlite_metadata_repository import SqliteMetadataRepository
from pipeline.application.ports.chat_model import ChatModelPort
from pipeline.application.use_cases.audit_concept_quality import AuditConceptQuality
from pipeline.application.use_cases.backfill_prerequisites import BackfillPrerequisites
from pipeline.application.use_cases.categorize_concepts import CategorizeConcepts
from pipeline.application.use_cases.category_materializer import CategoryMaterializer
from pipeline.application.use_cases.evaluate_prerequisites import EvaluatePrerequisites
from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.application.use_cases.ingest_raw_material import IngestRawMaterial
from pipeline.application.use_cases.knowledge_agent import KnowledgeAgent
from pipeline.application.use_cases.parse_source_documents import ParseSourceDocuments
from pipeline.application.use_cases.prune_stale_intake import PruneStaleIntake
from pipeline.application.use_cases.rebuild_index import RebuildIndex
from pipeline.application.use_cases.relevance_evidence_gatherer import (
    RelevanceEvidenceGatherer,
)
from pipeline.application.use_cases.scan_intake import ScanIntake
from pipeline.application.use_cases.search_concepts import SearchConcepts
from pipeline.application.use_cases.trace_lineage import TraceLineage
from pipeline.application.use_cases.validate_concept import ValidateConcept
from pipeline.config import ChatProvider, Settings
from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from pipeline.domain.intake import IntakeKind, IntakeState
from pipeline.logging_config import configure_logging

app = typer.Typer(help="Local-only ingestion + attester pipeline for the OKF vault.")


def _chat_client(settings: Settings, ollama: OllamaClient) -> ChatModelPort:
    """Resolves the configured provider. `ollama` is passed in rather than
    rebuilt so the local path shares one client with embeddings and vision."""
    if settings.chat_provider is ChatProvider.OPENROUTER:
        return OpenRouterClient(
            api_key=settings.openrouter_api_key or "",
            base_url=settings.openrouter_base_url,
            timeout=settings.ollama_timeout_seconds,
            max_tokens=settings.openrouter_max_tokens,
            max_retries=settings.ollama_max_retries,
            retry_backoff_seconds=settings.ollama_retry_backoff_seconds,
            reasoning=settings.openrouter_reasoning,
        )
    return ollama


class Container:
    """Wires every concrete local adapter to its port and builds the use cases.
    Swapping a piece of local tech later (e.g. ChromaDB -> another vector store)
    means writing one new adapter module and changing the corresponding line here
    — nothing in application/ or domain/ needs to change."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        self.raw_root = str(settings.vault_path / "raw")
        self.concept_repository = MarkdownConceptRepository(settings.vault_path)
        self.scanner = FilesystemScanner()
        self.intake_repository = SqliteIntakeRepository(settings.sqlite_path)
        self.raw_material_repository = FilesystemRawMaterialRepository(
            self.intake_repository, self.scanner
        )
        self.bundle_log = SqliteBundleLog(settings.sqlite_path)

        ollama = OllamaClient(
            settings.ollama_host,
            timeout=settings.ollama_timeout_seconds,
            max_predict_tokens=settings.ollama_max_predict_tokens,
            max_retries=settings.ollama_max_retries,
            retry_backoff_seconds=settings.ollama_retry_backoff_seconds,
        )
        # The provider seam (PRD v3 NFR1, issue #19). Only *text* skills move:
        # embeddings stay on `ollama` unconditionally, because every vector in
        # ChromaDB came from one embedding model and changing it invalidates
        # the index rather than improving it. Vision (image captioning) stays
        # local too — it is cheap, and it would otherwise ship page images of
        # every parsed PDF off the machine.
        chat: ChatModelPort = _chat_client(settings, ollama)

        self.embedding = OllamaEmbedding(ollama, settings.ollama_embed_model)
        self.extraction_skill = ExtractionSkill(chat, settings.chat_model)
        self.disambiguation_skill = EntityDisambiguationSkill(
            chat, settings.chat_model
        )
        self.type_classification_skill = TypeClassificationSkill(
            chat, settings.chat_model
        )
        self.domain_classification_skill = DomainClassificationSkill(
            chat, settings.chat_model
        )
        self.category_classification_skill = CategoryClassificationSkill(
            chat, settings.chat_model
        )
        self.quality_eval_skill = QualityEvalSkill(chat, settings.chat_model)
        self.quality_audit_skill = QualityAuditSkill(chat, settings.chat_model)
        self.relatedness_skill = RelatednessSkill(
            chat, settings.relatedness_model
        )
        self.prerequisite_judgement_skill = PrerequisiteJudgementSkill(
            chat, settings.chat_model
        )
        self.image_captioning_skill = OllamaImageCaptioningSkill(
            ollama, settings.ollama_vision_model
        )

        self.document_parser = DoclingDocumentParser(settings.parsed_images_dir)

        self.vector_search = ChromaVectorSearch(settings.chroma_dir)
        self.metadata_repository = SqliteMetadataRepository(settings.sqlite_path)
        self.schema_registry = JsonFileSchemaRegistry(settings.schemas_dir)
        self.eval_rubrics_repository = JsonFileEvalRubricsRepository(settings.evals_dir)

        self.index_concept = IndexConcept(
            self.embedding, self.vector_search, self.metadata_repository
        )
        self.audit_concept_quality = AuditConceptQuality(
            self.concept_repository, self.quality_audit_skill
        )
        self.relevance_evidence = RelevanceEvidenceGatherer(
            metadata_repository=self.metadata_repository,
            concept_repository=self.concept_repository,
            raw_material_repository=self.raw_material_repository,
        )
        self.knowledge_agent = KnowledgeAgent(
            extraction=self.extraction_skill,
            embedding=self.embedding,
            vector_search=self.vector_search,
            disambiguation=self.disambiguation_skill,
            type_classification=self.type_classification_skill,
            domain_classification=self.domain_classification_skill,
            category_classification=self.category_classification_skill,
            quality_eval=self.quality_eval_skill,
            relatedness=self.relatedness_skill,
            prerequisite_judgement=self.prerequisite_judgement_skill,
            relevance_evidence=self.relevance_evidence,
            eval_rubrics_repository=self.eval_rubrics_repository,
            metadata_repository=self.metadata_repository,
            concept_repository=self.concept_repository,
            disambiguation_confidence_threshold=settings.disambiguation_confidence_threshold,
            eval_threshold=settings.eval_threshold,
            relatedness_min_score=settings.relatedness_min_score,
            category_confidence_threshold=settings.category_confidence_threshold,
            prerequisite_threshold=settings.prerequisite_threshold,
            prerequisite_candidate_k=settings.prerequisite_candidate_k,
        )
        self.ingest_raw_material = IngestRawMaterial(
            raw_material_repository=self.raw_material_repository,
            knowledge_agent=self.knowledge_agent,
            concept_repository=self.concept_repository,
            index_concept=self.index_concept,
            bundle_log=self.bundle_log,
        )
        self.validate_concept = ValidateConcept(self.schema_registry)
        self.rebuild_index = RebuildIndex(self.concept_repository, self.index_concept)
        self.category_materializer = CategoryMaterializer(
            self.concept_repository, self.index_concept, self.bundle_log
        )
        self.backfill_prerequisites = BackfillPrerequisites(
            concept_repository=self.concept_repository,
            metadata_repository=self.metadata_repository,
            embedding=self.embedding,
            vector_search=self.vector_search,
            prerequisite_judgement=self.prerequisite_judgement_skill,
            eval_rubrics_repository=self.eval_rubrics_repository,
            index_concept=self.index_concept,
            threshold=settings.prerequisite_threshold,
            candidate_k=settings.prerequisite_candidate_k,
        )
        self.evaluate_prerequisites = EvaluatePrerequisites(
            concept_repository=self.concept_repository,
            prerequisite_judgement=self.prerequisite_judgement_skill,
            eval_rubrics_repository=self.eval_rubrics_repository,
            evals_dir=settings.evals_dir,
            threshold=settings.prerequisite_threshold,
        )
        self.categorize_concepts = CategorizeConcepts(
            concept_repository=self.concept_repository,
            metadata_repository=self.metadata_repository,
            category_classification=self.category_classification_skill,
            category_materializer=self.category_materializer,
            index_concept=self.index_concept,
            category_confidence_threshold=settings.category_confidence_threshold,
        )
        self.search_concepts = SearchConcepts(
            self.embedding,
            self.vector_search,
            self.metadata_repository,
            pool_k=settings.search_pool_k,
            graph_seed_k=settings.search_graph_seed_k,
            graph_max_hops=settings.search_graph_max_hops,
            graph_decay=settings.search_graph_decay,
            graph_category_decay=settings.search_graph_category_decay,
            rrf_k=settings.search_rrf_k,
            structured_min_results=settings.search_structured_min_results,
        )
        self.trace_lineage = TraceLineage(self.metadata_repository)
        self.scan_intake = ScanIntake(self.scanner, self.intake_repository)
        self.prune_stale_intake = PruneStaleIntake(self.intake_repository)
        self.parse_source_documents = ParseSourceDocuments(
            self.intake_repository,
            self.document_parser,
            self.image_captioning_skill,
            self.concept_repository,
            self.index_concept,
            self.bundle_log,
            max_chunk_chars=settings.chunk_max_chars,
        )


def _container() -> Container:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    return Container(settings)


@app.command()
def scan() -> None:
    """Discover new or changed files in vault/raw/ and register them for intake."""
    container = _container()
    new_items = container.scan_intake.run(container.raw_root)
    if not new_items:
        typer.echo("No new or changed files.")
        return
    for item in new_items:
        typer.echo(f"discovered {item.id[:12]}  {item.kind.value}  {item.path}")


@app.command()
def prune() -> None:
    """Delete stale intake items: rows superseded by a later hash at the same
    path that never got past `discovered`/`error`, so nothing was ever
    derived from them. `scan` already prevents new ones from piling up going
    forward — this cleans up ones that predate that (or slipped through
    another way)."""
    container = _container()
    removed = container.prune_stale_intake.run()
    if not removed:
        typer.echo("Nothing stale to prune.")
        return
    for item in removed:
        typer.echo(f"removed {item.id[:12]}  {item.kind.value}  {item.path}")


@app.command()
def status() -> None:
    """Show intake counts per (kind, state); list items needing attention."""
    container = _container()
    for state in IntakeState:
        for kind in IntakeKind:
            items = container.intake_repository.list_by_state(state, kind=kind)
            if items:
                typer.echo(f"{state.value:<10} {kind.value:<15} {len(items)}")

    for state in (IntakeState.REJECTED, IntakeState.ERROR):
        items = [
            item
            for kind in IntakeKind
            for item in container.intake_repository.list_by_state(state, kind=kind)
        ]
        for item in items:
            typer.echo(f"  [{state.value}] {item.id[:12]}  {item.path or item.id}  — {item.error_message}")


@app.command()
def retry(item_id: str) -> None:
    """Reset one intake item back to `discovered` so it re-enters the next run."""
    container = _container()
    item = container.intake_repository.get(item_id)
    if item is None:
        typer.echo(f"no intake item with id {item_id}")
        raise typer.Exit(code=1)
    item.state = IntakeState.DISCOVERED
    item.error_message = None
    container.intake_repository.upsert(item)
    typer.echo(f"reset {item_id[:12]} to discovered")


@app.command(name="parse-sources")
def parse_sources() -> None:
    """Parse binary source documents (PDF/PPTX/DOCX/XLSX/images) in vault/raw/ into
    chunks the ingest pipeline can consume."""
    container = _container()
    container.scan_intake.run(container.raw_root)
    outcomes = container.parse_source_documents.run()
    if not outcomes:
        typer.echo("No source documents to parse.")
        return
    for outcome in outcomes:
        if outcome.errored:
            typer.echo(f"error parsing {outcome.source_id[:12]}  — {outcome.errored}")
        else:
            skipped = f", {outcome.skipped} skipped as garbled" if outcome.skipped else ""
            typer.echo(
                f"parsed {outcome.source_id[:12]}  -> {len(outcome.chunk_ids)} chunk(s){skipped}"
            )


@app.command()
def ingest() -> None:
    """Ingest every unprocessed vault/raw/ item into draft concepts."""
    container = _container()
    container.scan_intake.run(container.raw_root)
    outcomes = container.ingest_raw_material.run()
    if not outcomes:
        typer.echo("Nothing to ingest.")
        return
    for outcome in outcomes:
        if outcome.errored:
            typer.echo(f"error raw/{outcome.raw_id}  — {outcome.errored}")
            continue
        for concept_id in outcome.created:
            typer.echo(f"created {concept_id}  (from raw/{outcome.raw_id})")
        for concept_id in outcome.merged_into:
            typer.echo(f"merged into {concept_id}  (from raw/{outcome.raw_id})")
        for reason in outcome.rejected:
            typer.echo(f"rejected raw/{outcome.raw_id}  — {reason}")


@app.command()
def validate(path: str) -> None:
    """Validate a concept against OKF conformance rules and its type's schema."""
    container = _container()
    concept_id = ConceptId(path[:-3] if path.endswith(".md") else path)
    concept = container.concept_repository.load(concept_id)
    result = container.validate_concept.run(concept)
    if result.ok:
        typer.echo(f"{concept_id}: conformant")
        return
    typer.echo(f"{concept_id}: NOT conformant")
    for issue in result.issues:
        typer.echo(f"  [{issue.field}] {issue.message}")
    raise typer.Exit(code=1)


@app.command()
def audit() -> None:
    """Flag concepts that don't stand alone as genuinely useful — a garbled
    table fragment (free, no LLM call), or anything QualityAuditSkillPort
    judges thin/vacuous. Purely a report; use `pipeline delete <id>` to
    actually remove one."""
    container = _container()
    flags = container.audit_concept_quality.run()
    if not flags:
        typer.echo("No low-quality concepts found.")
        return
    for flag in flags:
        typer.echo(f"{flag.concept_id}  — {flag.reason}")


@app.command(name="delete")
def delete_concept(path: str) -> None:
    """Remove one concept from the vault and its metadata/vector indices —
    the actual cleanup action for anything `pipeline audit` flags. Does not
    touch other concepts' links to it (broken links are tolerated by OKF §6;
    rewriting arbitrary other files isn't a deletion side effect)."""
    container = _container()
    concept_id = ConceptId(path[:-3] if path.endswith(".md") else path)
    if not container.concept_repository.exists(concept_id):
        typer.echo(f"no concept with id {concept_id}")
        raise typer.Exit(code=1)

    concept = container.concept_repository.load(concept_id)
    container.concept_repository.delete(concept_id)
    container.metadata_repository.delete(str(concept_id))
    container.vector_search.delete(str(concept_id))
    container.bundle_log.append(
        action="delete",
        concept_id=str(concept_id),
        raw_id=None,
        message=f"Removed {concept.frontmatter.title or concept_id}.",
    )
    typer.echo(f"deleted {concept_id}")


@app.command(name="index")
def index_command() -> None:
    """Rebuild the vector + metadata index from every concept in the vault."""
    container = _container()
    count = container.rebuild_index.run()
    typer.echo(f"indexed {count} concept(s)")


@app.command(name="new-domain")
def new_domain(
    slug: str,
    title: str = typer.Option(..., "--title"),
    description: str = typer.Option(..., "--description"),
) -> None:
    """Scaffold a new Domain concept in the vault plus a placeholder eval rubric
    file in pipeline/evals/ (dev-side quality validation — not vault content)."""
    container = _container()
    domain_id = ConceptId(f"domains/{slug}")

    if container.concept_repository.exists(domain_id):
        typer.echo(f"{domain_id} already exists.")
        raise typer.Exit(code=1)

    domain = Concept(
        id=domain_id,
        frontmatter=Frontmatter(type="Domain", title=title, description=description),
        body=f"# {title}\n\n*(no concepts yet — add links here as they're created)*\n",
    )
    container.concept_repository.save(domain)
    container.bundle_log.append(
        action="create", concept_id=str(domain_id), raw_id=None, message=f"Added Domain {title}."
    )

    rubrics_path = container.settings.evals_dir / f"{domain_id}.json"
    rubrics_path.parent.mkdir(parents=True, exist_ok=True)
    rubrics_path.write_text(
        json.dumps(
            [
                {
                    "rubric_id": "placeholder",
                    "rubric_content": {
                        "text_property": "Replace with a real, domain-specific quality criterion."
                    },
                    "type": "CONTENT_QUALITY",
                }
            ],
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    typer.echo(f"created {domain_id}")
    typer.echo(f"created {rubrics_path}")
    typer.echo("Link it from Home.md and fill in real eval rubrics.")


@app.command(name="log")
def log_command(limit: int = 20) -> None:
    """Show the pipeline's ingest audit trail (create/merge/reject decisions),
    newest first — the structured, queryable replacement for the old
    vault/log.md (WIKI_SPEC.md §9)."""
    container = _container()
    entries = container.bundle_log.list_entries()
    if not entries:
        typer.echo("No log entries yet.")
        return
    for entry in entries[:limit]:
        concept = f" concept={entry.concept_id}" if entry.concept_id else ""
        raw = f" raw={entry.raw_id[:12]}" if entry.raw_id else ""
        typer.echo(f"{entry.at.isoformat()}  {entry.action:<7}{concept}{raw}  {entry.message}")


@app.command()
def links(concept_id: str) -> None:
    """Show outgoing and incoming §6 links for one concept — the emergent
    cluster of related concepts around it, independent of tags."""
    container = _container()
    graph = container.metadata_repository.find_links(concept_id)
    typer.echo("outgoing:")
    for target in graph.outgoing:
        typer.echo(f"  {target}")
    typer.echo("incoming:")
    for source in graph.incoming:
        typer.echo(f"  {source}")


@app.command()
def search(
    query: str,
    k: int = 5,
    type: str = typer.Option(None, "--type", help="Structured prefilter: frontmatter type."),
    since: str = typer.Option(None, "--since", help="Structured prefilter: ISO date, inclusive."),
    until: str = typer.Option(None, "--until", help="Structured prefilter: ISO date, inclusive."),
) -> None:
    """Hybrid search over indexed concepts: vector + lexical (FTS5) fused via
    reciprocal rank fusion, then expanded/reranked through the link graph.
    Pass --type (optionally with --since/--until) to try a deterministic
    structured match first, falling back to the hybrid pipeline if it comes
    up short."""
    container = _container()
    matches = container.search_concepts.run(
        query,
        k=k,
        type=type,
        since=date.fromisoformat(since) if since else None,
        until=date.fromisoformat(until) if until else None,
    )
    for match in matches:
        typer.echo(f"{match.score:.3f}  {match.concept_id}")


@app.command()
def lineage(
    concept_id: str,
    relation_type: str = typer.Option(None, "--relation-type"),
    direction: str = typer.Option("both", "--direction", help="outgoing, incoming, or both."),
    max_hops: int = typer.Option(3, "--max-hops"),
) -> None:
    """Trace typed-relation chains from a concept (e.g. `supersedes` edges),
    up to --max-hops away — the full path, not just reachability."""
    container = _container()
    paths = container.trace_lineage.run(
        concept_id, relation_type=relation_type, direction=direction, max_hops=max_hops
    )
    if not paths:
        typer.echo("No typed-relation paths found.")
        return
    for path in paths:
        chain = " -> ".join(f"{link.relation_type}:{link.to_id}" for link in path)
        typer.echo(f"{concept_id} -> {chain}")


@app.command()
def categorize() -> None:
    """Backfill Category links for concepts that predate the ontology layer
    (everything ingested before `pipeline categorize` existed) — skips
    anything already categorized, domainless, or structural."""
    container = _container()
    count = container.categorize_concepts.run()
    typer.echo(f"categorized {count} concept(s)")


@app.command(name="mcp-serve")
def mcp_serve(
    host: str = typer.Option(None, "--host", help="Defaults to $MCP_HOST (127.0.0.1)."),
    port: int = typer.Option(None, "--port", help="Defaults to $MCP_PORT (8000)."),
    stateless: bool = typer.Option(
        None, "--stateless/--stateful", help="Defaults to $MCP_STATELESS (stateless)."
    ),
) -> None:
    """Serve the vault to MCP clients (e.g. Claude) over Streamable HTTP."""
    from pipeline.mcp.server import run as run_mcp_server

    settings = Settings.from_env()
    configure_logging(settings.log_level)
    run_mcp_server(
        host=host if host is not None else settings.mcp_host,
        port=port if port is not None else settings.mcp_port,
        stateless=stateless if stateless is not None else settings.mcp_stateless,
        auth_token=settings.mcp_auth_token,
    )


if __name__ == "__main__":
    app()


@app.command(name="eval-prerequisites")
def eval_prerequisites(
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show every pair, not just the failures."
    ),
) -> None:
    """Measure the prerequisite gate's precision against the human-labelled
    gold set (RF1.3). Exits non-zero below the 0.9 bar.

    Without this the gate is an LLM grading an LLM. Precision only: a wrong
    `requires::` edge sends the learner to study something they don't need and
    nothing downstream catches it, while a missed one costs the planner a
    dependency it could have used. Recall is reported but never gated."""
    container = _container()
    report = container.evaluate_prerequisites.run()

    for outcome in report.outcomes:
        is_failure = not outcome.correct and outcome.error is None
        if not (verbose or is_failure):
            continue
        marker = "ERR " if outcome.error else ("FAIL" if is_failure else "ok  ")
        tier = outcome.tier.value if outcome.tier else "(no edge)"
        expected = "requires" if outcome.pair.is_prerequisite else "not-a-prerequisite"
        typer.echo(
            f"{marker}  {outcome.pair.source} -> {outcome.pair.target}\n"
            f"        expected={expected}  got={tier}  avg={outcome.average_score:.2f}"
        )

    typer.echo("")
    if report.errored:
        typer.echo("")
        for outcome in report.errored:
            typer.echo(
                f"ERR   {outcome.pair.source} -> {outcome.pair.target}\n"
                f"        {outcome.error}"
            )

    typer.echo(f"pairs               {len(report.outcomes)}")
    typer.echo(f"measured            {len(report.measured)}  "
               f"({len(report.errored)} provider error(s), excluded)")
    typer.echo(f"emitted as requires {len(report.predicted)}")
    typer.echo(f"false positives     {len(report.false_positives)}")
    typer.echo(f"precision           {report.precision:.3f}  (bar {report.bar:.2f})")
    typer.echo(f"recall              {report.recall:.3f}  (not gated)")

    if not report.passed:
        typer.echo("")
        typer.echo("BELOW THE BAR - do not backfill (see `pipeline prerequisites`).")
        raise typer.Exit(code=1)


@app.command()
def prerequisites(
    limit: int = typer.Option(
        0, "--limit", "-n", help="Only process this many concepts (0 = all)."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show the edges without writing them."
    ),
) -> None:
    """Backfill `requires::` edges for concepts that predate the feature
    (RF1.4) — skips anything already carrying an edge, and anything
    structural. Idempotent: a second run changes nothing.

    Run `pipeline eval-prerequisites` first. The gate writes into the graph
    the study plan walks, and a model that has not cleared the 0.9 precision
    bar will emit roughly one wrong edge for every right one.

    On a cloud provider a full pass is hundreds of metered calls, so
    `--dry-run -n 5` is the cheap way to see what it would do first.
    """
    container = _container()
    outcomes = container.backfill_prerequisites.run(
        limit=limit or None, dry_run=dry_run
    )

    for outcome in outcomes:
        typer.echo(outcome.concept_id)
        for edge in outcome.edges:
            typer.echo(
                f"    {edge.relation_type:<12} {edge.target_id}  "
                f"({edge.eval.average_score:.2f})"
            )

    verb = "would emit" if dry_run else "emitted"
    typer.echo("")
    typer.echo(f"{verb} prerequisites for {len(outcomes)} concept(s)")
    if dry_run:
        typer.echo("dry run: nothing was written")

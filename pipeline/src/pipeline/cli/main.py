"""Composition root: the only place concrete local adapters (Ollama, ChromaDB,
SQLite, filesystem) get wired to the application's ports."""

from __future__ import annotations

import json

import typer

from pipeline.adapters.chroma.chroma_vector_search import ChromaVectorSearch
from pipeline.adapters.docling.document_parser import DoclingDocumentParser
from pipeline.adapters.eval_rubrics.json_file_eval_rubrics_repository import (
    JsonFileEvalRubricsRepository,
)
from pipeline.adapters.filesystem.filesystem_scanner import FilesystemScanner
from pipeline.adapters.filesystem.markdown_bundle_log import MarkdownBundleLog
from pipeline.adapters.filesystem.markdown_concept_repository import MarkdownConceptRepository
from pipeline.adapters.filesystem.raw_material_repository import FilesystemRawMaterialRepository
from pipeline.adapters.ollama.client import OllamaClient
from pipeline.adapters.ollama.embedding import OllamaEmbedding
from pipeline.adapters.ollama.skills.domain_classification import (
    OllamaDomainClassificationSkill,
)
from pipeline.adapters.ollama.skills.entity_disambiguation import (
    OllamaEntityDisambiguationSkill,
)
from pipeline.adapters.ollama.skills.extraction import OllamaExtractionSkill
from pipeline.adapters.ollama.skills.image_captioning import OllamaImageCaptioningSkill
from pipeline.adapters.ollama.skills.quality_eval import OllamaQualityEvalSkill
from pipeline.adapters.ollama.skills.type_classification import (
    OllamaTypeClassificationSkill,
)
from pipeline.adapters.schema_registry.json_file_schema_registry import (
    JsonFileSchemaRegistry,
)
from pipeline.adapters.sqlite.sqlite_intake_repository import SqliteIntakeRepository
from pipeline.adapters.sqlite.sqlite_metadata_repository import SqliteMetadataRepository
from pipeline.application.use_cases.index_concept import IndexConcept
from pipeline.application.use_cases.ingest_raw_material import IngestRawMaterial
from pipeline.application.use_cases.knowledge_agent import KnowledgeAgent
from pipeline.application.use_cases.parse_source_documents import ParseSourceDocuments
from pipeline.application.use_cases.rebuild_index import RebuildIndex
from pipeline.application.use_cases.scan_intake import ScanIntake
from pipeline.application.use_cases.search_concepts import SearchConcepts
from pipeline.application.use_cases.validate_concept import ValidateConcept
from pipeline.config import Settings
from pipeline.domain.concept import Concept, ConceptId, Frontmatter
from pipeline.domain.intake import IntakeKind, IntakeState
from pipeline.logging_config import configure_logging

app = typer.Typer(help="Local-only ingestion + attester pipeline for the OKF vault.")


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
        self.bundle_log = MarkdownBundleLog(settings.vault_path / "log.md")

        ollama = OllamaClient(
            settings.ollama_host,
            timeout=settings.ollama_timeout_seconds,
            max_predict_tokens=settings.ollama_max_predict_tokens,
            max_retries=settings.ollama_max_retries,
            retry_backoff_seconds=settings.ollama_retry_backoff_seconds,
        )
        self.embedding = OllamaEmbedding(ollama, settings.ollama_embed_model)
        self.extraction_skill = OllamaExtractionSkill(ollama, settings.ollama_chat_model)
        self.disambiguation_skill = OllamaEntityDisambiguationSkill(
            ollama, settings.ollama_chat_model
        )
        self.type_classification_skill = OllamaTypeClassificationSkill(
            ollama, settings.ollama_chat_model
        )
        self.domain_classification_skill = OllamaDomainClassificationSkill(
            ollama, settings.ollama_chat_model
        )
        self.quality_eval_skill = OllamaQualityEvalSkill(ollama, settings.ollama_chat_model)
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
        self.knowledge_agent = KnowledgeAgent(
            extraction=self.extraction_skill,
            embedding=self.embedding,
            vector_search=self.vector_search,
            disambiguation=self.disambiguation_skill,
            type_classification=self.type_classification_skill,
            domain_classification=self.domain_classification_skill,
            quality_eval=self.quality_eval_skill,
            eval_rubrics_repository=self.eval_rubrics_repository,
            metadata_repository=self.metadata_repository,
            concept_repository=self.concept_repository,
            disambiguation_confidence_threshold=settings.disambiguation_confidence_threshold,
            eval_threshold=settings.eval_threshold,
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
        self.search_concepts = SearchConcepts(self.embedding, self.vector_search)
        self.scan_intake = ScanIntake(self.scanner, self.intake_repository)
        self.parse_source_documents = ParseSourceDocuments(
            self.intake_repository,
            self.document_parser,
            self.image_captioning_skill,
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
        typer.echo(f"parsed {outcome.source_id[:12]}  -> {len(outcome.chunk_ids)} chunk(s)")


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
    container.bundle_log.append(f"**Creation**: Added Domain [{title}]({domain_id}.md).")

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
    typer.echo("Link it from MOC.md and fill in real eval rubrics.")


@app.command()
def search(query: str, k: int = 5) -> None:
    """Semantic search over indexed concepts."""
    container = _container()
    for match in container.search_concepts.run(query, k=k):
        typer.echo(f"{match.score:.3f}  {match.concept_id}")


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
    )


if __name__ == "__main__":
    app()

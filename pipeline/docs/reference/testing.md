# Testing

```bash
make test        # fast — excludes the `integration` marker (see below)
make test-all     # everything, including the slow/integration tests
```

(equivalent to `uv run pytest -q -m "not integration"` / `uv run pytest -q`,
if you'd rather call pytest directly — see `pipeline/Makefile` for the full
list of shortcuts.)

157 tests as of this writing, split into three tiers that mirror
`src/pipeline/`:

```
tests/
├── domain/         # pure functions/dataclasses — no fakes, no I/O, no markers
├── application/    # use cases against tests/application/fakes.py — no real adapters
├── adapters/       # real adapters — tmp_path for local I/O, @pytest.mark.integration for Ollama
└── conftest.py     # the `integration` marker + auto-skip fixture
```

## `tests/domain/`

Straight unit tests against pure functions and dataclasses:
`test_chunking.py`, `test_conformance.py`, `test_eval.py`, `test_intake.py`,
`test_lifecycle.py`, `test_trust.py`. No fixtures, no mocking — call the
function, assert on the result.

## `tests/application/` — use cases against fakes

Every port has a hand-written in-memory fake in
`tests/application/fakes.py` (`FakeConceptRepository`,
`FakeRawMaterialRepository`, `FakeEmbedding`, `FakeVectorSearch`,
`FakeExtractionSkill`, `FakeEntityDisambiguationSkill`,
`FakeDomainClassificationSkill`, `FakeTypeClassificationSkill`,
`FakeQualityEvalSkill`, `FakeEvalRubricsRepository`,
`FakeMetadataRepository`, `FakeBundleLog`, `FakeIntakeRepository`,
`FakeFileSystemScanner`, `FakeExecutor`, `FakeAttester`, ...). These are
plain Python classes backed by dicts/lists — no mocking framework, no real
Ollama/ChromaDB/SQLite. This is where `KnowledgeAgent`,
`IngestRawMaterial`, `IndexConcept`, `ScanIntake`, `ParseSourceDocuments`,
`ValidateConcept`, and `AttestComputation` are tested, driving each fake's
canned responses to exercise every branch (e.g. a fake disambiguation skill
returning high vs. low confidence to hit both the merge and create paths in
`KnowledgeAgent`).

**When you add a port**, add a fake for it here — every use case that
depends on it will need one, and a shared fake means later use cases don't
each reinvent one.

## `tests/adapters/` — real adapters

Exercises the actual adapter classes against real (but local/ephemeral)
backing storage:

- **Filesystem-backed adapters** (`test_filesystem.py`,
  `test_filesystem_scanner.py`, `test_raw_material_repository.py`) and
  **SQLite-backed adapters** (`test_sqlite_intake_repository.py`,
  `test_sqlite_metadata_repository.py`) use pytest's `tmp_path` fixture — a
  fresh temp directory/file per test, no shared state, no cleanup needed.
- **`test_chroma_vector_search.py`** does the same: `ChromaVectorSearch(tmp_path)`
  gives each test its own throwaway persistent collection.
- **`test_docling_parser.py`** generates a real PDF on the fly with `fpdf2`
  (a dev-only dependency — see `[dependency-groups].dev` in
  `pyproject.toml`) and asserts on what Docling extracts from it.
- **`test_json_file_eval_rubrics_repository.py`** and
  **`test_schema_registry_and_stubs.py`** read from `tmp_path`-written JSON
  files, and assert the stub `Executor`/`Attester` raise `NotImplementedError`.
- **`test_ollama_adapters.py`** is the one file that talks to a real Ollama
  instance — see the marker convention below.

## The `integration` marker — tests that need real Ollama

`tests/conftest.py` registers a custom marker and an autouse fixture:

```python
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: needs a real local service (e.g. Ollama) running"
    )

@pytest.fixture(scope="session")
def ollama_available() -> bool: ...   # pings http://localhost:11434/api/tags

@pytest.fixture(autouse=True)
def _skip_if_ollama_unavailable(request, ollama_available):
    if request.node.get_closest_marker("integration") and not ollama_available:
        pytest.skip("Ollama is not reachable at localhost:11434")
```

`tests/adapters/test_ollama_adapters.py` sets
`pytestmark = pytest.mark.integration` at module level, so every test in that
file auto-skips (rather than failing) when Ollama isn't running locally —
this is why `uv run pytest -q` passes cleanly in CI or on a machine without
Ollama, while still exercising real model calls when it's available. It
assumes the same default models as `config.py` (`llama3.1:8b`,
`qwen3-embedding:0.6b`) rather than reading `Settings` — if you change the
defaults, update the constants at the top of that file too.

**When you add a new adapter test that needs Ollama**, mark it
`@pytest.mark.integration` (or set `pytestmark` at module scope like
`test_ollama_adapters.py` does) so it participates in the same skip
behavior.

## Running a subset

```bash
uv run pytest tests/domain -q                 # fast, no I/O at all
uv run pytest tests/application -q            # use cases, still no real adapters
make test                                     # -m "not integration" — same split, via Makefile
make test-integration                         # only the integration-marked tests
uv run pytest tests/adapters/test_chroma_vector_search.py -q
```

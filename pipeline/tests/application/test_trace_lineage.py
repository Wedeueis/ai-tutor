from pipeline.application.use_cases.trace_lineage import TraceLineage
from pipeline.domain.concept import TypedLink
from tests.application.fakes import FakeMetadataRepository


def test_trace_lineage_delegates_to_metadata_repository():
    path = [TypedLink(from_id="a", to_id="b", relation_type="supersedes")]
    metadata_repository = FakeMetadataRepository(lineage_paths=[path])
    use_case = TraceLineage(metadata_repository)

    results = use_case.run("a")

    assert results == [path]

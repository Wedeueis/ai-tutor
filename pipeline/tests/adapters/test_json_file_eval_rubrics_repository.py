import json

from pipeline.adapters.eval_rubrics.json_file_eval_rubrics_repository import (
    JsonFileEvalRubricsRepository,
)

BASE_RUBRICS = [
    {
        "rubric_id": "traceable",
        "rubric_content": {"text_property": "Claims must be traceable to the source."},
        "type": "CONTENT_QUALITY",
    }
]
COFFEE_RUBRICS = [
    {
        "rubric_id": "quantitative",
        "rubric_content": {"text_property": "Ratios must be quantitative."},
    }
]


def test_falls_back_to_base_when_domain_has_no_file(tmp_path):
    (tmp_path / "_base.json").write_text(json.dumps(BASE_RUBRICS), encoding="utf-8")
    repo = JsonFileEvalRubricsRepository(tmp_path)

    rubrics = repo.load_for_domain("domains/unknown")

    assert len(rubrics) == 1
    assert rubrics[0].rubric_id == "traceable"
    assert rubrics[0].rubric_content.text_property == "Claims must be traceable to the source."
    assert rubrics[0].type == "CONTENT_QUALITY"


def test_prefers_domain_specific_file(tmp_path):
    (tmp_path / "_base.json").write_text(json.dumps(BASE_RUBRICS), encoding="utf-8")
    (tmp_path / "domains").mkdir()
    (tmp_path / "domains" / "coffee.json").write_text(json.dumps(COFFEE_RUBRICS), encoding="utf-8")
    repo = JsonFileEvalRubricsRepository(tmp_path)

    rubrics = repo.load_for_domain("domains/coffee")

    assert [r.rubric_id for r in rubrics] == ["quantitative"]


def test_none_domain_uses_base(tmp_path):
    (tmp_path / "_base.json").write_text(json.dumps(BASE_RUBRICS), encoding="utf-8")
    repo = JsonFileEvalRubricsRepository(tmp_path)

    rubrics = repo.load_for_domain(None)

    assert [r.rubric_id for r in rubrics] == ["traceable"]


def test_no_files_at_all_returns_empty(tmp_path):
    repo = JsonFileEvalRubricsRepository(tmp_path)
    assert repo.load_for_domain("domains/coffee") == []

import json

import pytest

from pipeline.adapters.schema_registry.json_file_schema_registry import JsonFileSchemaRegistry
from pipeline.adapters.stubs.not_implemented_attester import NotImplementedAttester
from pipeline.adapters.stubs.not_implemented_executor import NotImplementedExecutor


def test_falls_back_to_base_schema(tmp_path):
    (tmp_path / "_base.schema.json").write_text(json.dumps({"type": "object"}), encoding="utf-8")
    registry = JsonFileSchemaRegistry(tmp_path)

    assert registry.get_schema("SomeUnregisteredType") == {"type": "object"}


def test_prefers_type_specific_schema(tmp_path):
    (tmp_path / "_base.schema.json").write_text(json.dumps({"type": "object"}), encoding="utf-8")
    (tmp_path / "Playbook.schema.json").write_text(json.dumps({"required": ["title"]}), encoding="utf-8")
    registry = JsonFileSchemaRegistry(tmp_path)

    assert registry.get_schema("Playbook") == {"required": ["title"]}


def test_returns_none_when_nothing_registered(tmp_path):
    registry = JsonFileSchemaRegistry(tmp_path)
    assert registry.get_schema("Playbook") is None


def test_executor_stub_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        NotImplementedExecutor().run("SELECT 1", {})


def test_attester_stub_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        NotImplementedAttester().verify(receipt=None, contract={})

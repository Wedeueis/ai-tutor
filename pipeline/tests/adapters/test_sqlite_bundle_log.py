from datetime import datetime

from pipeline.adapters.sqlite.sqlite_bundle_log import SqliteBundleLog


def test_append_then_list_entries_newest_first(tmp_path):
    log = SqliteBundleLog(
        tmp_path / "metadata.db", clock=lambda: datetime(2026, 8, 9, 12, 0, 0)
    )

    log.append(action="create", concept_id="a", raw_id="raw-1", message="Added A.")
    log.append(action="merge", concept_id="b", raw_id="raw-2", message="Merged into B.")

    entries = log.list_entries()

    assert len(entries) == 2
    assert entries[0].action == "merge"
    assert entries[0].concept_id == "b"
    assert entries[0].raw_id == "raw-2"
    assert entries[0].at == datetime(2026, 8, 9, 12, 0, 0)
    assert entries[1].action == "create"
    log.close()


def test_reject_entries_have_no_concept_id(tmp_path):
    log = SqliteBundleLog(tmp_path / "metadata.db", clock=lambda: datetime(2026, 8, 9))

    log.append(action="reject", concept_id=None, raw_id="raw-1", message="failed eval")

    entries = log.list_entries()
    assert entries[0].concept_id is None
    assert entries[0].message == "failed eval"
    log.close()


def test_list_entries_empty_when_nothing_appended(tmp_path):
    log = SqliteBundleLog(tmp_path / "metadata.db")
    assert log.list_entries() == []
    log.close()

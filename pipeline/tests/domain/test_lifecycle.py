from datetime import date

from pipeline.domain.lifecycle import Status, effective_status, is_stale


def test_absent_status_is_stable():
    assert effective_status(None) is Status.STABLE


def test_explicit_status():
    assert effective_status("draft") is Status.DRAFT


def test_absent_stale_after_never_stale():
    assert is_stale(None, date(2099, 1, 1)) is False


def test_stale_on_or_after_date():
    assert is_stale("2026-09-23", date(2026, 9, 23)) is True
    assert is_stale("2026-09-23", date(2026, 9, 22)) is False

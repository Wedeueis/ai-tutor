from pipeline.domain.intake import IntakeKind, classify_kind


def test_classifies_raw_notes():
    assert classify_kind("note.md") is IntakeKind.RAW_NOTE
    assert classify_kind("note.txt") is IntakeKind.RAW_NOTE


def test_classifies_source_documents():
    for ext in ["pdf", "pptx", "docx", "xlsx", "png", "jpg", "jpeg"]:
        assert classify_kind(f"file.{ext}") is IntakeKind.SOURCE_DOCUMENT


def test_unrecognized_extension_returns_none():
    assert classify_kind("file.zip") is None
    assert classify_kind("README") is None


def test_classification_is_case_insensitive():
    assert classify_kind("Report.PDF") is IntakeKind.SOURCE_DOCUMENT


def test_files_under_raw_inquiries_are_not_intake_material():
    """`vault/raw/inquiries/` holds questions *about* the knowledge, not
    material to distil — ingesting one would produce a concept describing the
    gap rather than one filling it (see that folder's README)."""
    assert classify_kind("vault/raw/inquiries/missing-ease-factor.md") is None
    assert classify_kind("vault/raw/inquiries/some-paper.pdf") is None


def test_the_exclusion_is_a_path_segment_not_a_substring():
    assert classify_kind("vault/raw/inquiries-i-had.md") is IntakeKind.RAW_NOTE
    assert classify_kind("vault/raw/notes/inquiries.md") is IntakeKind.RAW_NOTE

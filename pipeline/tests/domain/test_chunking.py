from pipeline.domain.chunking import chunk_markdown


def test_empty_text_yields_no_chunks():
    assert chunk_markdown("") == []
    assert chunk_markdown("   ") == []


def test_short_document_is_a_single_chunk():
    text = "# Title\n\nSome short content."
    assert chunk_markdown(text, max_chars=4000) == [text]


def test_splits_by_top_level_headings():
    text = "# One\n\nfirst section\n\n# Two\n\nsecond section"
    chunks = chunk_markdown(text, max_chars=4000)
    assert len(chunks) == 2
    assert chunks[0].startswith("# One")
    assert chunks[1].startswith("# Two")


def test_leading_content_before_first_heading_becomes_its_own_chunk():
    text = "intro text\n\n# Heading\n\nbody"
    chunks = chunk_markdown(text, max_chars=4000)
    assert chunks[0] == "intro text"
    assert chunks[1].startswith("# Heading")


def test_oversized_section_falls_back_to_paragraph_split():
    paragraph = "word " * 50  # ~250 chars
    text = "# Big Section\n\n" + "\n\n".join([paragraph] * 10)  # well over max_chars
    chunks = chunk_markdown(text, max_chars=500)
    assert len(chunks) > 1
    assert all(len(c) <= 500 or "\n\n" not in c for c in chunks)


def test_single_paragraph_longer_than_max_chars_is_hard_split():
    text = "x" * 1000
    chunks = chunk_markdown(text, max_chars=300)
    assert all(len(c) <= 300 for c in chunks)
    assert "".join(chunks) == text

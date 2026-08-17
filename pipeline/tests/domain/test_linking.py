from pipeline.domain.agent import RelatedConcept
from pipeline.domain.concept import ConceptId
from pipeline.domain.linking import (
    add_footnote,
    add_link_section,
    add_related_links,
    cite,
    cite_body,
    insert_before_related,
)


def test_add_related_links_creates_section_when_absent():
    body = "Some content."
    links = [RelatedConcept(concept_id=ConceptId("a"), title="A", reason="reason")]

    result = add_related_links(body, links)

    assert result.startswith("Some content.")
    assert "## Related" in result
    assert "[A](/a.md) — reason" in result


def test_add_related_links_appends_to_existing_section():
    body = "Content.\n\n## Related\n\n- [A](/a.md) — reason a\n"
    links = [RelatedConcept(concept_id=ConceptId("b"), title="B", reason="reason b")]

    result = add_related_links(body, links)

    assert "[A](/a.md)" in result
    assert "[B](/b.md) — reason b" in result
    assert result.index("[A](/a.md)") < result.index("[B](/b.md)")


def test_add_related_links_dedupes_by_concept_id():
    body = "Content.\n\n## Related\n\n- [A](/a.md) — reason a\n"
    links = [RelatedConcept(concept_id=ConceptId("a"), title="A", reason="different reason")]

    result = add_related_links(body, links)

    assert result == body


def test_add_related_links_no_reason_omits_dash():
    body = "Content."
    links = [RelatedConcept(concept_id=ConceptId("a"), title="A", reason="")]

    result = add_related_links(body, links)

    assert "[A](/a.md)\n" in result
    assert "—" not in result


def test_add_related_links_empty_list_is_noop():
    body = "Content."

    assert add_related_links(body, []) == body


def test_add_link_section_uses_a_different_heading():
    body = "Source document stub."
    links = [RelatedConcept(concept_id=ConceptId("adam-optimizer"), title="Adam Optimizer")]

    result = add_link_section(body, "## Derived concepts", links)

    assert "## Derived concepts" in result
    assert "## Related" not in result
    assert "[Adam Optimizer](/adam-optimizer.md)" in result


def test_add_link_section_dedupes_independently_of_related():
    body = "Stub.\n\n## Derived concepts\n\n- [A](/a.md)\n"
    links = [RelatedConcept(concept_id=ConceptId("a"), title="A")]

    result = add_link_section(body, "## Derived concepts", links)

    assert result == body


def test_insert_before_related_places_addition_before_heading():
    body = "Original.\n\n## Related\n\n- [A](/a.md)\n"

    result = insert_before_related(body, "New merged content.")

    assert result.index("New merged content.") < result.index("## Related")
    assert "Original." in result
    assert "[A](/a.md)" in result


def test_insert_before_related_appends_normally_when_no_related_section():
    body = "Original."

    result = insert_before_related(body, "New merged content.")

    assert result == "Original.\n\nNew merged content."


def test_insert_before_related_keeps_related_last_across_multiple_merges():
    body = "Original.\n\n## Related\n\n- [A](/a.md)\n"

    once = insert_before_related(body, "First addition.")
    twice = insert_before_related(once, "Second addition.")

    assert twice.index("First addition.") < twice.index("## Related")
    assert twice.index("Second addition.") < twice.index("## Related")


# --- footnotes (WIKI_SPEC §5.1 per-claim attribution) ----------------------


def test_cite_marks_the_end_of_the_last_non_empty_line():
    """On its own line `[^label]` renders as a stray link, so the marker rides
    the text it attributes."""
    assert cite("A claim.\n", "book-p3") == "A claim.[^book-p3]"


def test_cite_is_idempotent():
    """Re-running ingest over the same passage must not stack markers."""
    once = cite("A claim.", "book-p3")

    assert cite(once, "book-p3") == once


def test_cite_leaves_empty_text_alone():
    assert cite("   \n\n", "book-p3") == "   \n\n"


def test_cite_body_skips_the_woven_link_sections():
    """A created concept already carries `## Categories` / `## Related` by the
    time it is stamped — citing its true last line would hang the marker off a
    link bullet."""
    body = "The prose.\n\n## Related\n\n- [x](/x.md)\n"

    cited = cite_body(body, "book-p3")

    assert "The prose.[^book-p3]" in cited
    assert "- [x](/x.md)" in cited
    assert "](/x.md)[^book-p3]" not in cited


def test_cite_body_falls_back_to_the_whole_body_when_there_are_no_sections():
    assert cite_body("Just prose.", "book-p3") == "Just prose.[^book-p3]"


def test_a_footnote_definition_is_added_under_its_own_heading():
    body = add_footnote("The prose.", "book-p3", "The Book — passage 3")

    assert "## Sources" in body
    assert "[^book-p3]: The Book — passage 3" in body


def test_footnote_definitions_are_deduped_by_label():
    once = add_footnote("The prose.", "book-p3", "The Book — passage 3")

    assert add_footnote(once, "book-p3", "something else") == once


def test_two_passages_each_get_their_own_definition():
    body = add_footnote(
        add_footnote("Prose.", "book-p3", "The Book — passage 3"),
        "book-p9",
        "The Book — passage 9",
    )

    assert body.count("## Sources") == 1
    assert "[^book-p3]:" in body
    assert "[^book-p9]:" in body


def test_related_stays_last_even_after_footnotes():
    """The module invariant: a trailing link section is always the body's last
    section."""
    body = "Prose.\n\n## Related\n\n- [x](/x.md)\n"

    body = add_footnote(body, "book-p3", "The Book — passage 3")

    assert body.rstrip().endswith("- [x](/x.md)")
    assert body.index("## Sources") < body.index("## Related")


def test_a_merge_addition_lands_before_the_footnote_list_not_inside_it():
    """Regression. `insert_before_related` used to aim at `## Related` alone,
    so an addition slid in *after* `## Sources` — landing a paragraph between
    two footnote definitions, where it reads as part of the footnote list and
    its marker is detached from the prose it attributes."""
    body = add_footnote("First claim.[^b-p3]", "b-p3", "The Book — passage 3")

    body = insert_before_related(body, cite("Second claim.", "b-p9"))
    body = add_footnote(body, "b-p9", "The Book — passage 9")

    prose_end = body.index("Second claim.")
    assert prose_end < body.index("## Sources")
    assert body.index("[^b-p3]: ") < body.index("[^b-p9]: ")


def test_prose_stays_ahead_of_every_trailing_section():
    body = (
        "Prose.\n\n## Sources\n\n[^a]: A\n\n## Categories\n\n- [c](/c.md)\n"
        "\n## Related\n\n- [r](/r.md)\n"
    )

    result = insert_before_related(body, "More prose.")

    assert result.index("More prose.") < result.index("## Sources")
    assert result.index("## Sources") < result.index("## Related")

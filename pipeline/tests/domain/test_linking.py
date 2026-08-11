from pipeline.domain.agent import RelatedConcept
from pipeline.domain.concept import ConceptId
from pipeline.domain.linking import add_link_section, add_related_links, insert_before_related


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

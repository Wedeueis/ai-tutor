"""Reading a concept back against the text it was distilled from."""

from __future__ import annotations

from pipeline.application.use_cases.recall_passages import MAX_CONTEXT, RecallPassages
from pipeline.domain.passage import Passage

HUB = "references/the-book"


def passage(ordinal: int, text: str = "") -> Passage:
    return Passage(
        id=f"chunk-{ordinal}",
        text=text or f"passage {ordinal} text",
        ordinal=ordinal,
        source_concept_id=HUB,
    )


class FakePassages:
    def __init__(self, for_concept: list[Passage], neighbours=None) -> None:
        self._for_concept = for_concept
        self._neighbours = neighbours or {}
        self.neighbour_calls: list[tuple[str, int]] = []

    def for_concept(self, concept_id: str) -> list[Passage]:
        return list(self._for_concept)

    def neighbours(self, passage_id: str, radius: int = 1) -> list[Passage]:
        self.neighbour_calls.append((passage_id, radius))
        return list(self._neighbours.get(passage_id, []))


# --- picking which passages ------------------------------------------------


def test_a_concept_with_no_passages_recalls_nothing():
    assert RecallPassages(FakePassages([])).run("a/b") == []


def test_every_contributing_passage_comes_back():
    recalled = RecallPassages(FakePassages([passage(3), passage(9)])).run(
        "a/b", context=0
    )

    assert [item.passage.ordinal for item in recalled] == [3, 9]


def test_a_source_id_narrows_to_one_claim():
    """The whole point of per-passage ids: check *this* claim, not the concept
    at large. The id is the same string the body's footnote carries."""
    recalled = RecallPassages(FakePassages([passage(3), passage(9)])).run(
        "a/b", source_id="the-book-p9", context=0
    )

    assert [item.passage.ordinal for item in recalled] == [9]


def test_an_unknown_source_id_recalls_nothing_rather_than_everything():
    recalled = RecallPassages(FakePassages([passage(3)])).run(
        "a/b", source_id="the-book-p999", context=0
    )

    assert recalled == []


def test_the_limit_only_applies_when_no_source_id_is_given():
    """A concept merged from many chunks would otherwise return the book — but
    asking for one specific citation must never be silently truncated."""
    many = [passage(n) for n in range(10)]

    assert len(RecallPassages(FakePassages(many)).run("a/b", context=0, limit=2)) == 2
    assert (
        len(
            RecallPassages(FakePassages(many)).run(
                "a/b", source_id="the-book-p7", context=0, limit=2
            )
        )
        == 1
    )


# --- context ---------------------------------------------------------------


def test_neighbours_are_split_into_before_and_after_by_ordinal():
    reader = FakePassages(
        [passage(5)],
        {"chunk-5": [passage(4, "earlier"), passage(6, "later")]},
    )

    recalled = RecallPassages(reader).run("a/b", context=1)[0]

    assert recalled.before == "earlier"
    assert recalled.after == "later"


def test_context_zero_never_asks_for_neighbours():
    reader = FakePassages([passage(5)])

    RecallPassages(reader).run("a/b", context=0)

    assert reader.neighbour_calls == []


def test_context_is_capped():
    """The caller is usually a local model with a small window, and a passage
    buried in six others stops being context and starts being the document."""
    reader = FakePassages([passage(5)])

    RecallPassages(reader).run("a/b", context=99)

    assert reader.neighbour_calls == [("chunk-5", MAX_CONTEXT)]


def test_a_negative_context_is_treated_as_none():
    reader = FakePassages([passage(5)])

    RecallPassages(reader).run("a/b", context=-1)

    assert reader.neighbour_calls == []


def test_a_passage_with_no_neighbours_has_no_context():
    recalled = RecallPassages(FakePassages([passage(0)])).run("a/b", context=1)[0]

    assert recalled.before is None and recalled.after is None


# --- truncation ------------------------------------------------------------


def test_before_keeps_its_tail_and_after_keeps_its_head():
    """Truncated from the inside out: the text nearest the passage is the text
    that explains it."""
    reader = FakePassages(
        [passage(5)],
        {"chunk-5": [passage(4, "A" * 50 + "NEAR"), passage(6, "NEAR" + "B" * 50)]},
    )

    recalled = RecallPassages(reader, context_chars=10).run("a/b", context=1)[0]

    assert recalled.before.endswith("NEAR")
    assert recalled.before.startswith("…")
    assert recalled.after.startswith("NEAR")
    assert recalled.after.endswith("…")


def test_short_context_is_not_truncated():
    reader = FakePassages([passage(5)], {"chunk-5": [passage(4, "short")]})

    recalled = RecallPassages(reader, context_chars=1000).run("a/b", context=1)[0]

    assert recalled.before == "short"


# --- the source id a passage carries --------------------------------------


def test_a_passage_derives_the_same_source_id_the_frontmatter_records():
    """`recall_passage` and `_add_source` must agree on the label without
    either parsing the other's output."""
    assert passage(17).source_id == "the-book-p17"


def test_a_passage_from_a_hand_written_note_has_no_source_id():
    """No parsed document, so no `references/` hub and nothing to cite."""
    orphan = Passage(id="note-1", text="a note", ordinal=None)

    assert orphan.source_id is None
    assert orphan.locator is None

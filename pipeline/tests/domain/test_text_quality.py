from pipeline.domain.text_quality import looks_like_garbled_table

# A real excerpt from a Docling table-parse artifact (Table 3 of the
# "Attention Is All You Need" paper) — the chunk that originally produced
# four near-meaningless concepts.
GARBLED_TABLE_EXCERPT = """
|      |                                           |                                           |                                           |               |        6.11 |         23.7 | 36              |
|      | 4                                         |                                           |                                           |               |        5.19 |         25.3 | 50              |
|      | 8                                         |                                           |                                           |               |        4.88 |         25.5 | 80              |
| (C)  |                                           | 256                                       |                                           |               |        5.75 |         24.5 | 28              |
|      |                                           | 1024                                      |                                           |               |        4.66 |         26.0 | 168             |
"""

GOOD_PROSE = (
    "The Adam optimizer is a popular stochastic gradient descent optimizer "
    "that adapts the learning rate for each parameter. It uses the first "
    "and second moments of the gradients to update the parameters, which "
    "can help improve convergence speed and stability."
)


def test_garbled_table_is_flagged():
    assert looks_like_garbled_table(GARBLED_TABLE_EXCERPT) is True


def test_real_prose_is_not_flagged():
    assert looks_like_garbled_table(GOOD_PROSE) is False


def test_short_text_is_inconclusive_not_flagged():
    assert looks_like_garbled_table("| 4 |") is False


def test_empty_text_is_not_flagged():
    assert looks_like_garbled_table("") is False

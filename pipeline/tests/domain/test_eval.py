from pipeline.domain.eval import RubricScore, aggregate_scores


def test_average_above_threshold_passes():
    scores = [RubricScore("a", 0.9), RubricScore("b", 0.8)]
    result = aggregate_scores(scores, threshold=0.7)
    assert result.passed
    assert round(result.average_score, 2) == 0.85


def test_average_below_threshold_fails():
    scores = [RubricScore("a", 0.5), RubricScore("b", 0.4)]
    result = aggregate_scores(scores, threshold=0.7)
    assert not result.passed
    assert round(result.average_score, 2) == 0.45


def test_average_equal_to_threshold_passes():
    scores = [RubricScore("a", 0.7)]
    result = aggregate_scores(scores, threshold=0.7)
    assert result.passed


def test_no_scores_fails():
    result = aggregate_scores([], threshold=0.7)
    assert not result.passed
    assert result.average_score == 0.0


def test_none_scores_are_excluded_from_average():
    scores = [RubricScore("a", None), RubricScore("b", 1.0)]
    result = aggregate_scores(scores, threshold=0.7)
    assert result.average_score == 1.0
    assert result.passed


def test_all_none_scores_fails():
    scores = [RubricScore("a", None), RubricScore("b", None)]
    result = aggregate_scores(scores, threshold=0.7)
    assert not result.passed
    assert result.average_score == 0.0


def test_result_preserves_the_original_scores():
    scores = [RubricScore("a", 0.9, "good"), RubricScore("b", 0.2, "bad")]
    result = aggregate_scores(scores, threshold=0.7)
    assert result.scores == scores

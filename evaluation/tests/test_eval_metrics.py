import math

import pytest

from scitech_eval.metrics import bootstrap_ci, mean, recall_at_k, reciprocal_rank


def test_recall_counts_distinct_documents_in_top_k():
    # top-5 chunks come from documents x, a, a, y, z: only a of {a, b} is found
    assert recall_at_k({"a", "b"}, ["x", "a", "a", "y", "z", "b"], 5) == 0.5
    assert recall_at_k({"a", "b"}, ["x", "a", "a", "y", "z", "b"], 6) == 1.0
    assert recall_at_k({"a", "b"}, ["x", "a", "a", "y", "z", "b"], 1) == 0.0


def test_recall_with_fewer_results_than_k():
    assert recall_at_k({"a"}, ["a"], 10) == 1.0
    assert recall_at_k({"a"}, [], 10) == 0.0


def test_recall_needs_a_relevant_document():
    with pytest.raises(ValueError):
        recall_at_k(set(), ["a"], 5)


def test_reciprocal_rank_counts_chunk_positions():
    assert reciprocal_rank({"a"}, ["a", "x"]) == 1.0
    assert reciprocal_rank({"a"}, ["x", "a"]) == 0.5
    # two chunks of the same wrong document both take a rank
    assert reciprocal_rank({"a"}, ["x", "x", "a"]) == pytest.approx(1 / 3)


def test_reciprocal_rank_is_zero_without_hit_in_top_10():
    assert reciprocal_rank({"a"}, ["x"] * 10 + ["a"]) == 0.0
    assert reciprocal_rank({"a"}, ["x", "y"]) == 0.0
    assert reciprocal_rank({"a"}, ["x"] * 9 + ["a"]) == pytest.approx(0.1)


def test_bootstrap_of_constant_values_is_that_value():
    assert bootstrap_ci([0.5] * 7) == (0.5, 0.5)


def test_bootstrap_is_reproducible_and_brackets_the_mean():
    values = [0.0, 1.0, 1.0, 0.0, 1.0, 0.5, 0.0, 1.0]
    first = bootstrap_ci(values, seed=3)
    assert first == bootstrap_ci(values, seed=3)
    low, high = first
    assert 0.0 <= low <= mean(values) <= high <= 1.0
    assert low < high


def test_bootstrap_needs_values():
    with pytest.raises(ValueError):
        bootstrap_ci([])


def test_mean():
    assert math.isclose(mean([1, 2, 3, 6]), 3.0)

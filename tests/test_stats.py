import pytest

from voting.stats import average_ranks, spearman


def test_average_ranks_descending():
    assert average_ranks({"a": 10, "b": 5, "c": 1}) == {"a": 1.0, "b": 2.0, "c": 3.0}


def test_tied_values_share_the_average_rank():
    # two values tied for ranks 1 and 2 both get 1.5
    assert average_ranks({"a": 10, "b": 10, "c": 1}) == {"a": 1.5, "b": 1.5, "c": 3.0}


def test_perfect_agreement_is_one():
    crowd = {"a": 3, "b": 2, "c": 1}
    panel = {"a": 30, "b": 20, "c": 10}
    assert spearman(crowd, panel) == pytest.approx(1.0)


def test_perfect_disagreement_is_minus_one():
    crowd = {"a": 3, "b": 2, "c": 1}
    panel = {"a": 10, "b": 20, "c": 30}
    assert spearman(crowd, panel) == pytest.approx(-1.0)


def test_known_value():
    # ranks a..e = 1..5 vs 2,1,4,3,5 -> d^2 sum = 1+1+1+1+0 = 4
    # rho = 1 - (6*4) / (5 * 24) = 1 - 24/120 = 0.8
    crowd = {"a": 50, "b": 40, "c": 30, "d": 20, "e": 10}
    panel = {"a": 40, "b": 50, "c": 20, "d": 30, "e": 10}
    assert spearman(crowd, panel) == pytest.approx(0.8)


def test_returns_none_when_a_side_has_no_variance():
    """All-tied input has zero standard deviation; correlation is undefined, not zero."""
    assert spearman({"a": 1, "b": 1}, {"a": 2, "b": 1}) is None


def test_returns_none_below_two_items():
    assert spearman({"a": 1}, {"a": 1}) is None

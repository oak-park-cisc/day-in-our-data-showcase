"""C1: tie-aware crowd ranking, per spec §6.3.

"Because picks are unranked, there is no principled way to break a tie in
approval count from the ballot data — so the tally does not invent one.
Tied projects share a rank and are displayed as tied. If a tie falls on a
gift-card boundary, it is flagged in `vote.json` and CISC decides."
"""
from __future__ import annotations

from voting.ranking import (
    DEFAULT_AWARD_COUNT,
    competition_ranks,
    ranking_summary,
    tie_groups,
)


def test_competition_ranks_share_a_rank_and_skip_the_ones_they_consumed():
    ranks = competition_ranks({"a": 9, "b": 5, "c": 5, "d": 2})
    assert ranks == {"a": 1, "b": 2, "c": 2, "d": 4}


def test_competition_ranks_never_order_ties_by_id():
    # Submission id must not be a tiebreak: both tied projects get rank 1,
    # regardless of which id sorts first.
    assert competition_ranks({"sub_009": 4, "sub_001": 4}) == {"sub_009": 1, "sub_001": 1}


def test_tie_groups_lists_only_genuine_ties_best_first():
    assert tie_groups({"a": 9, "b": 5, "c": 5, "d": 2, "e": 2}) == [["b", "c"], ["d", "e"]]


def test_no_tie_groups_when_every_count_is_distinct():
    assert tie_groups({"a": 3, "b": 2, "c": 1}) == []


def test_tie_straddling_the_award_boundary_is_flagged():
    # Three gift cards; 3rd and 4th place tie. CISC must decide.
    summary = ranking_summary({"a": 9, "b": 7, "c": 5, "d": 5}, award_count=3)
    assert summary["ranks"]["c"] == 3
    assert summary["ranks"]["d"] == 3
    assert summary["award_boundary_tie"] is True
    assert summary["award_boundary_tie_ids"] == ["c", "d"]
    assert summary["award_count"] == 3


def test_tie_entirely_inside_the_award_set_is_not_a_boundary_tie():
    summary = ranking_summary({"a": 9, "b": 9, "c": 5, "d": 2}, award_count=3)
    assert summary["ranks"] == {"a": 1, "b": 1, "c": 3, "d": 4}
    assert summary["award_boundary_tie"] is False
    assert summary["award_boundary_tie_ids"] == []


def test_tie_entirely_outside_the_award_set_is_not_a_boundary_tie():
    summary = ranking_summary({"a": 9, "b": 7, "c": 5, "d": 2, "e": 2}, award_count=3)
    assert summary["award_boundary_tie"] is False


def test_a_tie_spanning_the_boundary_from_above_is_flagged():
    # Four-way tie at the top with three gift cards: one of the four misses out.
    summary = ranking_summary({"a": 6, "b": 6, "c": 6, "d": 6, "e": 1}, award_count=3)
    assert summary["award_boundary_tie"] is True
    assert summary["award_boundary_tie_ids"] == ["a", "b", "c", "d"]


def test_award_count_is_configurable():
    counts = {"a": 9, "b": 5, "c": 5, "d": 2}
    assert ranking_summary(counts, award_count=1)["award_boundary_tie"] is False
    assert ranking_summary(counts, award_count=2)["award_boundary_tie"] is True


def test_no_boundary_exists_when_every_project_is_awarded():
    summary = ranking_summary({"a": 5, "b": 5}, award_count=DEFAULT_AWARD_COUNT)
    assert summary["award_boundary_tie"] is False


def test_empty_counts_are_handled():
    summary = ranking_summary({}, award_count=3)
    assert summary["ranking"] == []
    assert summary["ranks"] == {}
    assert summary["ties"] == []
    assert summary["award_boundary_tie"] is False

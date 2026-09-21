"""C1 at the build_comparison layer: tied crowd counts must reach the page as
shared ranks, with a tie for first place flagged as a shared win (spec §6.3,
amended 2026-09-21: one winner, no gift cards; ties for first share the win).
"""
from __future__ import annotations

from judging.prompts import PERSONAS
from voting.compare import build_comparison
from voting.tally import TallyResult


def _ranking_fixture():
    # sub_003 and sub_004 tie for third on 5 votes each -- with one winner
    # that tie sits well outside the award cut.
    result = TallyResult(
        counts={"sub_001": 9, "sub_002": 7, "sub_003": 5, "sub_004": 5},
        valid=12,
        invalid=0,
        indicative=False,
    )
    scores = {f"P-0{i}": {p: 3 for p in PERSONAS} for i in range(1, 5)}
    id_of = {f"P-0{i}": f"sub_00{i}" for i in range(1, 5)}
    return result, scores, id_of


def _first_place_tie_fixture():
    # sub_001 and sub_002 tie for first on 9 votes each -- with one winner
    # that tie IS the award boundary: both win.
    result = TallyResult(
        counts={"sub_001": 9, "sub_002": 9, "sub_003": 5, "sub_004": 2},
        valid=12,
        invalid=0,
        indicative=False,
    )
    scores = {f"P-0{i}": {p: 3 for p in PERSONAS} for i in range(1, 5)}
    id_of = {f"P-0{i}": f"sub_00{i}" for i in range(1, 5)}
    return result, scores, id_of


def test_tied_crowd_counts_share_a_rank_rather_than_being_ordered_by_id():
    result, scores, id_of = _ranking_fixture()
    out = build_comparison(result, scores, list(id_of), id_of)
    assert out["crowd_ranks"]["sub_003"] == 3
    assert out["crowd_ranks"]["sub_004"] == 3
    assert out["crowd_ties"] == [["sub_003", "sub_004"]]


def test_tie_outside_the_award_cut_is_not_flagged_at_the_default_award_count():
    # One winner: a tie for third never touches the boundary.
    result, scores, id_of = _ranking_fixture()
    out = build_comparison(result, scores, list(id_of), id_of)
    assert out["award_boundary_tie"] is False
    assert out["award_boundary_tie_ids"] == []
    assert out["award_count"] == 1


def test_tie_for_first_is_flagged_as_a_shared_win_at_the_default_award_count():
    result, scores, id_of = _first_place_tie_fixture()
    out = build_comparison(result, scores, list(id_of), id_of)
    assert out["award_boundary_tie"] is True
    assert out["award_boundary_tie_ids"] == ["sub_001", "sub_002"]
    assert out["award_count"] == 1


def test_award_boundary_is_configurable_from_build_comparison():
    # The constant is not hardcoded downstream: an explicit award_count of 3
    # still reaches the boundary check and still flags the tie it spans.
    result, scores, id_of = _ranking_fixture()
    out = build_comparison(result, scores, list(id_of), id_of, award_count=3)
    assert out["award_boundary_tie"] is True
    assert out["award_boundary_tie_ids"] == ["sub_003", "sub_004"]
    assert out["award_count"] == 3

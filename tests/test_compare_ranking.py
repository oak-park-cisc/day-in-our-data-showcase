"""C1 at the build_comparison layer: tied crowd counts must reach the page as
shared ranks, with a tie on the gift-card boundary flagged for CISC (spec 6.3).
"""
from __future__ import annotations

from judging.prompts import PERSONAS
from voting.compare import build_comparison
from voting.tally import TallyResult


def _ranking_fixture():
    # sub_003 and sub_004 tie for third on 5 votes each; with three gift
    # cards that tie falls exactly on the award boundary.
    result = TallyResult(
        counts={"sub_001": 9, "sub_002": 7, "sub_003": 5, "sub_004": 5},
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


def test_tie_on_the_gift_card_boundary_is_flagged_for_cisc():
    result, scores, id_of = _ranking_fixture()
    out = build_comparison(result, scores, list(id_of), id_of)
    assert out["award_boundary_tie"] is True
    assert out["award_boundary_tie_ids"] == ["sub_003", "sub_004"]
    assert out["award_count"] == 3


def test_award_boundary_is_configurable_from_build_comparison():
    result, scores, id_of = _ranking_fixture()
    out = build_comparison(result, scores, list(id_of), id_of, award_count=2)
    assert out["award_boundary_tie"] is False
    assert out["award_count"] == 2

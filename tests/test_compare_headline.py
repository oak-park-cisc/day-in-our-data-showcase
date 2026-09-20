"""I1 at the comparison layer: the headline coefficient must correlate the
crowd against the panel's BRACKET FINISH, not against pass-1 mean scores.

Pass 2 is roughly 130 of the panel's ~200 API calls. Correlating means would
mean none of them reached the published finding.
"""
from __future__ import annotations

from voting.compare import build_comparison
from voting.tally import TallyResult

ID_OF = {"P-01": "sub_001", "P-02": "sub_002", "P-03": "sub_003"}


def _fixture():
    # The crowd's order matches the bracket finish exactly and is the exact
    # reverse of the mean-score order, so the two coefficients cannot be
    # confused for one another: one is +1, the other -1.
    result = TallyResult(
        counts={"sub_001": 9, "sub_002": 6, "sub_003": 3},
        valid=14,
        invalid=0,
        indicative=False,
    )
    scores = {
        "P-01": {"civic-impact": 2, "craft": 2},
        "P-02": {"civic-impact": 3, "craft": 3},
        "P-03": {"civic-impact": 5, "craft": 5},
    }
    finish = ["P-01", "P-02", "P-03"]
    return result, scores, finish


def test_headline_spearman_uses_bracket_finish_not_mean_score():
    result, scores, finish = _fixture()
    out = build_comparison(result, scores, finish, ID_OF)
    assert out["spearman"] == 1.0, (
        "the headline must correlate the crowd against the bracket finish; "
        "-1.0 here means it is still correlating pass-1 means"
    )


def test_mean_based_coefficient_is_kept_as_a_labelled_secondary():
    result, scores, finish = _fixture()
    out = build_comparison(result, scores, finish, ID_OF)
    assert out["spearman_by_mean"] == -1.0
    assert out["spearman_basis"] == "bracket finish"


def test_panel_means_still_populate_the_secondary_column():
    result, scores, finish = _fixture()
    out = build_comparison(result, scores, finish, ID_OF)
    assert out["panel_means"] == {"sub_001": 2.0, "sub_002": 3.0, "sub_003": 5.0}


def test_headline_is_undefined_when_the_panel_has_not_ranked_anything():
    result, scores, _ = _fixture()
    out = build_comparison(result, scores, [], ID_OF)
    assert out["spearman"] is None
    assert out["panel_ranking"] == []

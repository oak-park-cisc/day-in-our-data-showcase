from voting.compare import build_comparison
from voting.generate_codes import generate_codes
from voting.tally import TallyResult


def test_codes_are_unique_and_long_enough_to_resist_guessing():
    codes = generate_codes(40)
    assert len(set(codes)) == 40
    assert all(len(c) >= 10 for c in codes)


def test_comparison_reports_both_rankings_and_agreement():
    result = TallyResult(
        counts={"sub_001": 9, "sub_002": 6, "sub_003": 3}, valid=12, invalid=0, indicative=False
    )
    scores = {"P-01": {"a": 5}, "P-02": {"a": 4}, "P-03": {"a": 3}}
    id_of = {"P-01": "sub_001", "P-02": "sub_002", "P-03": "sub_003"}
    out = build_comparison(result, scores, ["P-01", "P-02", "P-03"], id_of)
    assert out["crowd_ranking"] == ["sub_001", "sub_002", "sub_003"]
    assert out["spearman"] == 1.0
    assert out["indicative"] is False


def test_indicative_turnout_is_flagged_and_correlation_caveated():
    result = TallyResult(counts={"sub_001": 2, "sub_002": 1}, valid=3, invalid=0, indicative=True)
    out = build_comparison(
        result, {"P-01": {"a": 5}, "P-02": {"a": 4}}, ["P-01", "P-02"],
        {"P-01": "sub_001", "P-02": "sub_002"},
    )
    assert out["indicative"] is True
    assert out["caveat"]


def test_per_persona_agreement_is_reported():
    result = TallyResult(
        counts={"sub_001": 9, "sub_002": 6, "sub_003": 3}, valid=12, invalid=0, indicative=False
    )
    scores = {
        "P-01": {"civic-impact": 5, "craft": 1},
        "P-02": {"civic-impact": 4, "craft": 3},
        "P-03": {"civic-impact": 3, "craft": 5},
    }
    id_of = {"P-01": "sub_001", "P-02": "sub_002", "P-03": "sub_003"}
    out = build_comparison(result, scores, ["P-01", "P-02", "P-03"], id_of)
    assert out["per_persona"]["civic-impact"] == 1.0
    assert out["per_persona"]["craft"] == -1.0

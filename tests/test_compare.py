from judging.prompts import PERSONAS
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
    # Every persona must score a submission for it to count (I3), so these
    # fixtures carry a full panel rather than one stand-in judge.
    scores = {
        "P-01": {p: 5 for p in PERSONAS},
        "P-02": {p: 4 for p in PERSONAS},
        "P-03": {p: 3 for p in PERSONAS},
    }
    id_of = {"P-01": "sub_001", "P-02": "sub_002", "P-03": "sub_003"}
    out = build_comparison(result, scores, ["P-01", "P-02", "P-03"], id_of)
    assert out["crowd_ranking"] == ["sub_001", "sub_002", "sub_003"]
    assert out["spearman"] == 1.0
    assert out["indicative"] is False


def test_indicative_turnout_is_flagged_and_correlation_caveated():
    result = TallyResult(counts={"sub_001": 2, "sub_002": 1}, valid=3, invalid=0, indicative=True)
    out = build_comparison(
        result,
        {"P-01": {p: 5 for p in PERSONAS}, "P-02": {p: 4 for p in PERSONAS}},
        ["P-01", "P-02"],
        {"P-01": "sub_001", "P-02": "sub_002"},
    )
    assert out["indicative"] is True
    assert out["caveat"]


def test_per_persona_agreement_is_reported():
    result = TallyResult(
        counts={"sub_001": 9, "sub_002": 6, "sub_003": 3}, valid=12, invalid=0, indicative=False
    )
    # civic-impact tracks the crowd exactly; craft is its mirror image. The
    # remaining personas are held constant so their correlation is undefined
    # rather than accidentally meaningful.
    def panel(civic: int, craft: int) -> dict[str, int]:
        scored = {p: 3 for p in PERSONAS}
        scored["civic-impact"] = civic
        scored["craft"] = craft
        return scored

    scores = {"P-01": panel(5, 1), "P-02": panel(4, 3), "P-03": panel(3, 5)}
    id_of = {"P-01": "sub_001", "P-02": "sub_002", "P-03": "sub_003"}
    out = build_comparison(result, scores, ["P-01", "P-02", "P-03"], id_of)
    assert out["per_persona"]["civic-impact"] == 1.0
    assert out["per_persona"]["craft"] == -1.0

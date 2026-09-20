"""I3: one rule for which submissions the panel is deemed to have scored.

judging/run_panel.py required all 5 personas before a submission could be
seeded, bracketed or ranked. voting/compare.py accepted any non-empty score
dict. So a submission where a persona abstained twice vanished from the
panel's ranking -- yet its mean still entered the headline correlation,
computed over 2 personas against everyone else's 5.

Owner decision: exclude from both, and disclose. Spec §8 requires the
exclusion be "shown in the UI. Never silent."
"""
from __future__ import annotations

import json
from pathlib import Path

from judging.client import MockJudgeClient
from judging.inclusion import panel_scored, split_scored
from judging.models import load_submissions
from judging.prompts import PERSONAS
from judging.run_panel import run
from judging.schemas import MatchupOutput, ScoreOutput
from voting.compare import build_comparison
from voting.tally import TallyResult

FIXTURES = Path(__file__).parent / "fixtures"

FULL = {persona: 3 for persona in PERSONAS}
PARTIAL = {PERSONAS[0]: 5, PERSONAS[1]: 5}


def test_a_submission_scored_by_every_persona_is_included():
    assert panel_scored(FULL) is True


def test_a_submission_missing_a_persona_is_excluded():
    assert panel_scored(PARTIAL) is False
    assert panel_scored({}) is False


def test_extra_unknown_personas_do_not_disqualify_a_full_score():
    assert panel_scored(dict(FULL, **{"a-sixth-judge": 4})) is True


def test_split_scored_partitions_and_sorts_the_exclusions():
    included, excluded = split_scored({"P-01": FULL, "P-03": PARTIAL, "P-02": {}})
    assert included == {"P-01": FULL}
    assert excluded == ["P-02", "P-03"]


# ---- the two modules now agree ----


def _comparison_with_a_partial_submission():
    result = TallyResult(
        counts={"sub_001": 9, "sub_002": 6, "sub_003": 3},
        valid=14,
        invalid=0,
        indicative=False,
    )
    scores = {
        # Distinct scores, so each persona's correlation against the crowd is
        # defined rather than undefined-for-lack-of-variation.
        "P-01": {persona: 4 for persona in PERSONAS},
        "P-02": {persona: 2 for persona in PERSONAS},
        # Three personas abstained twice on P-03. run_panel drops it from
        # seeding, the bracket and the ranking; compare must drop it too.
        # Its surviving scores are deliberately the HIGHEST while the crowd
        # ranked it LAST, so admitting it would push every per-persona
        # correlation away from +1.0.
        "P-03": PARTIAL,
    }
    id_of = {"P-01": "sub_001", "P-02": "sub_002", "P-03": "sub_003"}
    return result, scores, id_of


def test_a_partially_scored_submission_never_enters_the_headline_correlation():
    result, scores, id_of = _comparison_with_a_partial_submission()
    out = build_comparison(result, scores, ["P-01", "P-02"], id_of)
    assert "sub_003" not in out["panel_means"]
    assert "sub_003" not in out["panel_ranking"]


def test_a_partially_scored_submission_never_enters_a_per_persona_correlation():
    result, scores, id_of = _comparison_with_a_partial_submission()
    out = build_comparison(result, scores, ["P-01", "P-02"], id_of)
    # PERSONAS[0] scored all three; only the two complete ones may count.
    assert out["per_persona"][PERSONAS[0]] is not None
    # With sub_003 excluded, the two remaining projects agree perfectly;
    # including sub_003's 5 would drag it to a different value.
    assert out["per_persona"][PERSONAS[0]] == 1.0


def test_excluded_submissions_are_disclosed_by_public_id():
    result, scores, id_of = _comparison_with_a_partial_submission()
    out = build_comparison(result, scores, ["P-01", "P-02"], id_of)
    assert out["panel_abstained"] == ["sub_003"]


def test_nothing_is_disclosed_when_every_submission_was_fully_scored():
    result, scores, id_of = _comparison_with_a_partial_submission()
    scores = dict(scores, **{"P-03": {persona: 1 for persona in PERSONAS}})
    out = build_comparison(result, scores, ["P-01", "P-02", "P-03"], id_of)
    assert out["panel_abstained"] == []


def test_run_panel_applies_the_same_rule(tmp_path: Path):
    subs = load_submissions(FIXTURES / "submissions.json")
    # Drop one persona's response for the first submission: score_all records
    # an abstention, leaving it with 4 of 5 scores.
    canned: list = []
    for index in range(len(subs)):
        for position in range(5):
            if index == 0 and position == 2:
                canned.append(None)
            else:
                canned.append(ScoreOutput(score=4, justification="g", evidence=["d"]))
    canned += [MatchupOutput(winner="A", reasoning="c")] * 4000
    run(subs, MockJudgeClient(canned), tmp_path)

    scores = json.loads((tmp_path / "scores.json").read_text())["scores"]
    bracket = json.loads((tmp_path / "bracket.json").read_text())
    assert len(scores["P-01"]) == 4, "fixture should leave P-01 short one persona"
    assert "P-01" not in bracket["ranking"]
    assert "P-01" not in bracket["seeds"]
    # And the same rule, applied by compare, keeps it out of the statistics
    # while disclosing it.
    result = TallyResult(
        counts={f"sub_00{i}": 10 - i for i in range(1, 7)}, valid=14, invalid=0, indicative=False
    )
    id_of = {f"P-0{i}": f"sub_00{i}" for i in range(1, 7)}
    out = build_comparison(result, scores, bracket["ranking"], id_of)
    assert "sub_001" not in out["panel_means"]
    assert out["panel_abstained"] == ["sub_001"]

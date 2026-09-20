"""I1: the published panel ranking must be the bracket's finish order, not
pass-1 seeding.

`run_panel` used to compute `ranking` from the seeds *before* the bracket ran
and never touch it again, so results.html could head the "Panel chose" column
with P-01 while the champion pane directly below named P-06 — the page
contradicting itself in one eye-span — and the headline Spearman correlated
the crowd against pass-1 means, making pass 2 (~130 of ~200 API calls)
contribute nothing to the published finding.
"""
from __future__ import annotations

import json
from pathlib import Path

from judging.bracket import finish_order
from judging.client import MockJudgeClient
from judging.models import load_submissions
from judging.run_panel import run
from judging.schemas import MatchupOutput, ScoreOutput

FIXTURES = Path(__file__).parent / "fixtures"


def _rounds_four_seeds():
    """A 4-entrant bracket in which the bottom seed wins it all.

    Seeds: P-01=1, P-02=2, P-03=3, P-04=4. Round 1 pairs 1v4 and 2v3;
    the underdogs win both, then P-04 beats P-03 in the final.
    """
    return [
        [
            {"a": "P-01", "b": "P-04", "winner": "P-04", "bye": False},
            {"a": "P-02", "b": "P-03", "winner": "P-03", "bye": False},
        ],
        [{"a": "P-04", "b": "P-03", "winner": "P-04", "bye": False}],
    ]


SEEDS_FOUR = {"P-01": 1, "P-02": 2, "P-03": 3, "P-04": 4}


def test_finish_order_puts_the_champion_first_not_the_top_seed():
    order = finish_order(_rounds_four_seeds(), SEEDS_FOUR, champion="P-04")
    assert order[0] == "P-04"


def test_runner_up_is_second_and_first_round_losers_trail():
    order = finish_order(_rounds_four_seeds(), SEEDS_FOUR, champion="P-04")
    assert order == ["P-04", "P-03", "P-01", "P-02"]


def test_same_round_eliminations_break_by_seed_not_by_id():
    # P-01 (seed 1) and P-02 (seed 2) both went out in round 1; the better
    # seed places higher. Reverse the seed numbers and the order flips, which
    # proves the ordering is not alphabetical on anon_id.
    flipped = {"P-01": 4, "P-02": 3, "P-03": 2, "P-04": 1}
    order = finish_order(_rounds_four_seeds(), flipped, champion="P-04")
    assert order == ["P-04", "P-03", "P-02", "P-01"]


def test_a_bye_is_not_an_elimination():
    rounds = [
        [
            {"a": "P-01", "b": None, "winner": "P-01", "bye": True},
            {"a": "P-02", "b": "P-03", "winner": "P-03", "bye": False},
        ],
        [{"a": "P-01", "b": "P-03", "winner": "P-03", "bye": False}],
    ]
    order = finish_order(rounds, {"P-01": 1, "P-02": 2, "P-03": 3}, champion="P-03")
    assert order == ["P-03", "P-01", "P-02"]


def test_entrants_that_never_played_still_appear_ordered_by_seed():
    order = finish_order(
        _rounds_four_seeds(),
        dict(SEEDS_FOUR, **{"P-05": 5, "P-06": 6}),
        champion="P-04",
    )
    assert order[-2:] == ["P-05", "P-06"]


def test_finish_order_without_a_champion_still_ranks_everyone():
    order = finish_order(_rounds_four_seeds(), SEEDS_FOUR, champion=None)
    assert sorted(order) == ["P-01", "P-02", "P-03", "P-04"]


# ---- run_panel wiring ----


def _responses(n_subs: int, winner: str) -> list:
    out = [ScoreOutput(score=4, justification="Grounded.", evidence=["description"])] * (n_subs * 5)
    out += [MatchupOutput(winner=winner, reasoning="Cited.")] * 4000
    return out


def test_published_ranking_is_headed_by_the_champion_not_the_top_seed(tmp_path: Path):
    subs = load_submissions(FIXTURES / "submissions.json")
    # Every persona answers "B" both ways, so the swap never confirms and the
    # higher seed advances -- deterministic, and the champion is seed 1. Use
    # "A"/"B" alternation instead so B-side entrants actually win matchups.
    responses = [ScoreOutput(score=4, justification="Grounded.", evidence=["description"])] * (
        len(subs) * 5
    )
    # For each persona pair (forward, swapped): "B" then "A" both name the
    # second-listed submission, so the B side wins every confirmed matchup.
    responses += [MatchupOutput(winner=w, reasoning="Cited.") for _ in range(2000) for w in ("B", "A")]
    run(subs, MockJudgeClient(responses), tmp_path)

    bracket = json.loads((tmp_path / "bracket.json").read_text())
    assert bracket["mode"] == "bracket"
    assert bracket["champion"], "fixture should produce a champion"
    assert bracket["ranking"][0] == bracket["champion"], (
        "the published ranking must be headed by the bracket's champion; "
        f"got {bracket['ranking'][0]!r} with champion {bracket['champion']!r}"
    )
    # The seeding order is retained separately for the audit trail.
    assert bracket["seed_ranking"][0] == min(bracket["seeds"], key=bracket["seeds"].get)


def test_ranked_list_fallback_still_publishes_the_seed_order(tmp_path: Path):
    subs = load_submissions(FIXTURES / "submissions.json")[:3]
    run(subs, MockJudgeClient(_responses(3, "A")), tmp_path)
    bracket = json.loads((tmp_path / "bracket.json").read_text())
    assert bracket["mode"] == "ranked_list"
    assert len(bracket["ranking"]) == 3
    assert bracket["ranking"] == bracket["seed_ranking"]

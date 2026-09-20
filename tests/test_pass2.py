from pathlib import Path

from judging.client import MockJudgeClient
from judging.models import load_submissions
from judging.pass2 import judge_matchup
from judging.schemas import MatchupOutput

FIXTURES = Path(__file__).parent / "fixtures"
SEEDS = {"P-01": 1, "P-02": 2}


def pick(side: str) -> MatchupOutput:
    return MatchupOutput(winner=side, reasoning="Because of the cited evidence.")


def two_subs():
    subs = load_submissions(FIXTURES / "submissions.json")
    return subs[0], subs[1]


def test_consistent_judge_vote_is_confirmed():
    a, b = two_subs()
    # normal order: A wins. swapped order: B wins (B is now the original A).
    client = MockJudgeClient([pick("A"), pick("B")] * 5)
    record = judge_matchup(client, a, b, SEEDS)
    assert all(v.swap_confirmed for v in record.votes)
    assert record.winner == "P-01"


def test_position_biased_judge_is_not_counted():
    a, b = two_subs()
    # always picks whatever is in slot A - the classic position bias
    client = MockJudgeClient([pick("A"), pick("A")] * 5)
    record = judge_matchup(client, a, b, SEEDS)
    assert not any(v.swap_confirmed for v in record.votes)
    assert record.winner == "P-01"  # all abstained -> higher seed


def test_refusal_in_either_direction_abstains():
    a, b = two_subs()
    client = MockJudgeClient([pick("A"), None] * 5)
    record = judge_matchup(client, a, b, SEEDS)
    assert not any(v.swap_confirmed for v in record.votes)


def test_each_persona_is_called_twice():
    a, b = two_subs()
    client = MockJudgeClient([pick("A"), pick("B")] * 5)
    judge_matchup(client, a, b, SEEDS)
    assert len(client.calls) == 10

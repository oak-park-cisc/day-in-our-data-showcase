from pathlib import Path

from judging.client import MockJudgeClient
from judging.models import load_submissions
from judging.pass1 import score_all
from judging.schemas import ScoreOutput

FIXTURES = Path(__file__).parent / "fixtures"


def ok(n: int) -> ScoreOutput:
    return ScoreOutput(score=n, justification="Grounded.", evidence=["description"])


def test_scores_every_submission_with_every_persona():
    subs = load_submissions(FIXTURES / "submissions.json")
    client = MockJudgeClient([ok(4)] * (len(subs) * 5))
    result = score_all(client, subs)
    assert len(result.scores) == len(subs)
    assert all(len(p) == 5 for p in result.scores.values())


def test_abstention_is_recorded_and_excluded():
    subs = load_submissions(FIXTURES / "submissions.json")[:1]
    client = MockJudgeClient([ok(4), None, ok(3), ok(3), ok(3)])
    result = score_all(client, subs)
    assert len(result.abstentions) == 1
    assert len(result.scores["P-01"]) == 4


def test_judges_never_receive_the_team_name():
    subs = load_submissions(FIXTURES / "submissions.json")
    client = MockJudgeClient([ok(4)] * (len(subs) * 5))
    score_all(client, subs)
    sent = " ".join(user for _, user in client.calls)
    for s in subs:
        assert s.team_name not in sent

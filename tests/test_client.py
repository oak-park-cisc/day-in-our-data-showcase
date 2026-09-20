from judging.client import MockJudgeClient
from judging.schemas import MatchupOutput, ScoreOutput


def test_mock_returns_queued_score():
    c = MockJudgeClient([ScoreOutput(score=4, justification="Clear civic use.", evidence=["README"])])
    out = c.score("sys", "user")
    assert out.score == 4


def test_mock_returns_none_for_queued_abstention():
    c = MockJudgeClient([None])
    assert c.score("sys", "user") is None


def test_score_rejects_empty_evidence():
    """A verdict with no evidence is not a verdict."""
    import pydantic, pytest

    with pytest.raises(pydantic.ValidationError):
        ScoreOutput(score=4, justification="Looks good.", evidence=[])


def test_score_rejects_out_of_range():
    import pydantic, pytest

    with pytest.raises(pydantic.ValidationError):
        ScoreOutput(score=6, justification="x", evidence=["y"])


def test_matchup_records_winner_and_reasoning():
    m = MatchupOutput(winner="A", reasoning="A cites its sources; B does not.")
    assert m.winner == "A"

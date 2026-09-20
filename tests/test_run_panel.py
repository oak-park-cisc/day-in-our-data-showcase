import json
from pathlib import Path

from judging.client import MockJudgeClient
from judging.models import load_submissions
from judging.run_panel import run
from judging.schemas import MatchupOutput, ScoreOutput

FIXTURES = Path(__file__).parent / "fixtures"


def responses(n_subs: int) -> list:
    out = [ScoreOutput(score=4, justification="Grounded.", evidence=["description"])] * (n_subs * 5)
    out += [MatchupOutput(winner=w, reasoning="Cited.") for _ in range(200) for w in ("A", "B")]
    return out


def test_writes_scores_and_bracket(tmp_path: Path):
    subs = load_submissions(FIXTURES / "submissions.json")
    run(subs, MockJudgeClient(responses(len(subs))), tmp_path)
    assert (tmp_path / "scores.json").exists()
    assert (tmp_path / "bracket.json").exists()


def test_bracket_names_a_single_champion(tmp_path: Path):
    subs = load_submissions(FIXTURES / "submissions.json")
    run(subs, MockJudgeClient(responses(len(subs))), tmp_path)
    bracket = json.loads((tmp_path / "bracket.json").read_text())
    assert bracket["champion"] in {s.anon_id for s in subs}


def test_transcripts_are_written_for_every_submission(tmp_path: Path):
    subs = load_submissions(FIXTURES / "submissions.json")
    run(subs, MockJudgeClient(responses(len(subs))), tmp_path)
    files = list((tmp_path / "transcripts").glob("*.json"))
    assert len(files) >= len(subs)


def test_fewer_than_four_submissions_degrades_to_a_ranked_list(tmp_path: Path):
    subs = load_submissions(FIXTURES / "submissions.json")[:3]
    run(subs, MockJudgeClient(responses(3)), tmp_path)
    bracket = json.loads((tmp_path / "bracket.json").read_text())
    assert bracket["mode"] == "ranked_list"
    assert len(bracket["ranking"]) == 3


def test_every_transcript_file_carries_the_model_generated_flag(tmp_path: Path):
    subs = load_submissions(FIXTURES / "submissions.json")
    run(subs, MockJudgeClient(responses(len(subs))), tmp_path)

    score_files = sorted((tmp_path / "transcripts").glob("score-*.json"))
    round_files = sorted((tmp_path / "transcripts").glob("round-*.json"))
    assert score_files, "expected at least one score transcript"
    assert round_files, "expected at least one round transcript"

    for path in score_files:
        payload = json.loads(path.read_text())
        assert payload["model_generated"] is True
        assert "justifications" in payload

    for path in round_files:
        payload = json.loads(path.read_text())
        assert payload["model_generated"] is True
        assert "matchups" in payload

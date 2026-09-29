from pathlib import Path

from judging.models import load_submissions
from judging.prompts import PERSONAS, evidence_block, load_persona, matchup_user

FIXTURES = Path(__file__).parent / "fixtures"


def test_six_personas_exist():
    assert len(PERSONAS) == 6
    assert "data-provenance" in PERSONAS


def test_every_persona_states_code_is_not_required():
    for name in PERSONAS:
        text = load_persona(name).lower()
        assert "code is not required" in text, f"{name} may penalise non-coders"


def test_every_persona_demands_evidence():
    for name in PERSONAS:
        assert "evidence" in load_persona(name).lower()


def test_evidence_block_never_contains_the_team_name():
    sub = next(s for s in load_submissions(FIXTURES / "submissions.json") if s.id == "sub_001")
    block = evidence_block(sub)
    assert sub.team_name not in block
    assert sub.anon_id in block


def test_evidence_block_marks_missing_material():
    sub = next(s for s in load_submissions(FIXTURES / "submissions.json") if s.id == "sub_005")
    block = evidence_block(sub)
    assert "(not provided)" in block


def test_matchup_user_labels_sides_a_and_b():
    text = matchup_user("ALPHA", "BETA")
    assert "Submission A" in text and "Submission B" in text


def test_no_persona_penalises_a_project_for_not_using_ai():
    for name in PERSONAS:
        text = " ".join(load_persona(name).lower().split())
        assert "traditional" in text, f"{name} must say non-AI projects are judged the same"
        assert ("not part of your score" in text) or ("neither a plus nor a minus" in text), name


def test_the_provenance_judge_asks_for_a_traceable_path_from_raw_data():
    text = " ".join(load_persona("data-provenance").lower().split())
    assert "raw data" in text and "rerun" in text
    assert "no traceable origin" in text

"""Covering tests for the inline tally logic embedded in
.github/workflows/tally.yml.

Fix (per coordinator review of task-16-report.md): missing data/ballots.json
or data/submissions.json used to surface as a bare FileNotFoundError
traceback in the Actions log; it now prints one clear line naming the
ordering dependency (run sync-submissions.yml first) and exits 1.

These tests extract the exact Python heredoc body from the workflow file
itself -- no YAML parser involved (PyYAML isn't a project dependency; this
project deliberately keeps its dependency list to anthropic+pydantic), just
a plain-text heredoc extraction plus textwrap.dedent, which is sufficient
because the workflow file's block-scalar indentation is uniform by
construction. Extracting from the real file (rather than a hand-copied
duplicate of the logic) means there is no drift risk between what's tested
here and what actually ships in tally.yml.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from judging.prompts import PERSONAS

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "tally.yml"


def _extract_tally_script() -> str:
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "python - <<'PY'")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "PY")
    body = "\n".join(lines[start + 1 : end])
    return textwrap.dedent(body)


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def _run_script(cwd: Path) -> subprocess.CompletedProcess:
    script = _extract_tally_script()
    script_path = cwd / "_extracted_tally.py"
    script_path.write_text(script, encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["BALLOT_CODES"] = "CODE001,CODE002,CODE003"
    return subprocess.run(
        [sys.executable, str(script_path)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def test_extracted_script_is_syntactically_valid():
    script = _extract_tally_script()
    compile(script, "<tally.yml>", "exec")  # raises SyntaxError if the heredoc body is broken


def test_exits_nonzero_with_a_clear_message_when_both_files_missing(tmp_path):
    result = _run_script(tmp_path)
    assert result.returncode == 1
    assert "data/submissions.json" in result.stderr
    assert "data/ballots.json" in result.stderr
    assert "sync-submissions.yml" in result.stderr
    assert "Traceback" not in result.stderr  # the whole point of the fix


def test_exits_nonzero_with_a_clear_message_when_only_ballots_missing(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "submissions.json").write_text("[]", encoding="utf-8")

    result = _run_script(tmp_path)
    assert result.returncode == 1
    assert "data/ballots.json" in result.stderr
    assert "data/submissions.json" not in result.stderr  # names only what's actually missing
    assert "sync-submissions.yml" in result.stderr
    assert "Traceback" not in result.stderr


def test_exits_nonzero_with_a_clear_message_when_only_submissions_missing(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "ballots.json").write_text("[]", encoding="utf-8")

    result = _run_script(tmp_path)
    assert result.returncode == 1
    assert "data/submissions.json" in result.stderr
    assert "data/ballots.json" not in result.stderr
    assert "Traceback" not in result.stderr


def _write_fixture_data(data_dir: Path) -> None:
    data_dir.mkdir()
    (data_dir / "submissions.json").write_text(json.dumps([
        {"id": "sub_001", "anon_id": "P-01"},
        {"id": "sub_002", "anon_id": "P-02"},
        {"id": "sub_003", "anon_id": "P-03"},
    ]), encoding="utf-8")
    ballots = [
        {
            "code_hash": _hash_code("CODE001"),
            "picks": ["sub_001", "sub_002", "sub_003"],
            "cast_at": "2026-10-03T16:05:00Z",
        },
    ]
    (data_dir / "ballots.json").write_text(json.dumps(ballots), encoding="utf-8")


def test_succeeds_and_writes_vote_json_when_both_files_present(tmp_path):
    data_dir = tmp_path / "data"
    _write_fixture_data(data_dir)

    result = _run_script(tmp_path)
    assert result.returncode == 0, result.stderr

    vote = json.loads((data_dir / "results" / "vote.json").read_text())
    assert vote["valid"] == 1
    assert vote["invalid"] == 0
    assert vote["counts"]["sub_001"] == 1

    comparison = json.loads((data_dir / "results" / "comparison.json").read_text())
    # No bracket.json/scores.json yet (judge.yml hasn't run) -> crowd-only fallback.
    assert comparison["spearman"] is None
    assert comparison["panel_ranking"] == []
    assert comparison["caveat"] == "AI panel results are not published yet."


def test_succeeds_with_full_comparison_when_judge_results_already_exist(tmp_path):
    data_dir = tmp_path / "data"
    _write_fixture_data(data_dir)
    results_dir = data_dir / "results"
    results_dir.mkdir()
    (results_dir / "bracket.json").write_text(json.dumps({
        "ranking": ["P-01", "P-02", "P-03"],
    }), encoding="utf-8")
    # A full panel: I3's inclusion rule drops any submission a persona did
    # not score, so a one-persona fixture would now be excluded outright.
    (results_dir / "scores.json").write_text(json.dumps({
        "scores": {
            "P-01": {p: 4 for p in PERSONAS},
            "P-02": {p: 3 for p in PERSONAS},
            "P-03": {p: 2 for p in PERSONAS},
        },
    }), encoding="utf-8")

    result = _run_script(tmp_path)
    assert result.returncode == 0, result.stderr

    comparison = json.loads((results_dir / "comparison.json").read_text())
    assert comparison["panel_ranking"] == ["sub_001", "sub_002", "sub_003"]
    assert comparison["panel_means"]["sub_001"] == 4.0
    assert comparison["caveat"] != "AI panel results are not published yet."


# ---- C1: vote.json carries the tie information CISC needs (spec §6.3) ----


def _write_tied_fixture_data(data_dir: Path) -> None:
    """Three ballots over four projects, engineered so sub_002, sub_003 and
    sub_004 all finish on two votes -- a three-way tie for second that spans
    positions 2, 3 and 4 and therefore straddles the third gift card."""
    data_dir.mkdir()
    (data_dir / "submissions.json").write_text(json.dumps([
        {"id": f"sub_00{i}", "anon_id": f"P-0{i}"} for i in range(1, 5)
    ]), encoding="utf-8")
    ballots = [
        {"code_hash": _hash_code("CODE001"),
         "picks": ["sub_001", "sub_002", "sub_003"],
         "cast_at": "2026-10-03T16:05:00Z"},
        {"code_hash": _hash_code("CODE002"),
         "picks": ["sub_001", "sub_002", "sub_004"],
         "cast_at": "2026-10-03T16:06:00Z"},
        {"code_hash": _hash_code("CODE003"),
         "picks": ["sub_001", "sub_003", "sub_004"],
         "cast_at": "2026-10-03T16:07:00Z"},
    ]
    (data_dir / "ballots.json").write_text(json.dumps(ballots), encoding="utf-8")


def test_vote_json_shares_a_rank_for_tied_projects_and_flags_the_award_boundary(tmp_path):
    data_dir = tmp_path / "data"
    _write_tied_fixture_data(data_dir)

    result = _run_script(tmp_path)
    assert result.returncode == 0, result.stderr

    vote = json.loads((data_dir / "results" / "vote.json").read_text())
    assert vote["counts"] == {"sub_001": 3, "sub_002": 2, "sub_003": 2, "sub_004": 2}
    # Shared rank, not 2/3/4 by submission id.
    assert vote["ranks"] == {"sub_001": 1, "sub_002": 2, "sub_003": 2, "sub_004": 2}
    assert vote["ties"] == [["sub_002", "sub_003", "sub_004"]]
    # Three gift cards, three projects tied across the third -- CISC decides.
    assert vote["award_count"] == 3
    assert vote["award_boundary_tie"] is True
    assert vote["award_boundary_tie_ids"] == ["sub_002", "sub_003", "sub_004"]

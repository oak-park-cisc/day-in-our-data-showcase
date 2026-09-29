"""event-day.yml: the two-button workflow the event team runs (decision log #39)."""
from __future__ import annotations

from pathlib import Path

import yaml

WF = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _load(name: str) -> dict:
    data = yaml.safe_load((WF / name).read_text(encoding="utf-8"))
    # PyYAML reads the bare key `on` as boolean True.
    data["on"] = data.pop(True, data.get("on"))
    return data


def test_event_day_is_manual_only_with_two_labelled_steps():
    wf = _load("event-day.yml")
    assert set(wf["on"]) == {"workflow_dispatch"}, "event day must never run on a timer"
    options = wf["on"]["workflow_dispatch"]["inputs"]["step"]["options"]
    assert [o[:1] for o in options] == ["1", "2", "0"]
    assert "Open voting" in options[0] and "Close voting" in options[1]
    assert "site owner only" in options[2]


def test_judging_is_real_only_on_close_voting():
    job = _load("event-day.yml")["jobs"]["judge"]
    # mock is true exactly for the rehearsal; open voting never runs judging.
    assert job["with"]["mock"] == "${{ startsWith(inputs.step, '0') }}"
    assert "'1'" not in job["if"]


def test_rehearsal_never_deploys():
    job = _load("event-day.yml")["jobs"]["deploy"]
    assert "'0'" not in job["if"]
    assert "startsWith(inputs.step, '2') && needs.tally.result == 'success'" in job["if"]


def test_the_vote_tally_does_not_depend_on_judging_succeeding():
    job = _load("event-day.yml")["jobs"]["tally"]
    assert "always()" in job["if"]
    assert "needs.sync.result == 'success'" in job["if"]


def test_presses_queue_instead_of_racing():
    wf = _load("event-day.yml")
    assert wf["concurrency"]["cancel-in-progress"] is False


def test_called_workflows_accept_workflow_call_and_check_out_latest_main():
    for name in ["sync-submissions.yml", "judge.yml", "tally.yml"]:
        wf = _load(name)
        assert "workflow_call" in wf["on"], name
        text = (WF / name).read_text(encoding="utf-8")
        assert "ref: ${{ github.ref }}" in text, f"{name} would check out a stale commit"
        assert "git pull --rebase" in text, name


def test_judge_still_defaults_to_mock_when_run_by_hand():
    wf = _load("judge.yml")
    assert wf["on"]["workflow_dispatch"]["inputs"]["mock"]["default"] is True
    assert wf["on"]["workflow_call"]["inputs"]["mock"]["default"] is True


def test_team_guide_links_the_workflow_page():
    guide = (WF.parent.parent / "docs" / "event-day-buttons.md").read_text(encoding="utf-8")
    assert "actions/workflows/event-day.yml" in guide

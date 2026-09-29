"""What the panel is told about each submission must be true.

I8 (original): the panel was once told a working repository was
"unavailable" when nothing had tried to fetch it. The owner's first ruling was
to state accurately that repositories were not fetched.

Decision log #38 (owner decision, 2026-09-29): the panel now reads each
team's README -- from an uploaded zip or the linked GitHub repository -- via
judging.readmes. These tests hold the new methodology to the same standard:
a README that was read is shown fenced and labelled as participant data; a
submission without one gets a note that does not call anything
"unavailable"; and results.html says what the panel actually read.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from judging.client import MockJudgeClient
from judging.models import Submission, load_submissions
from judging.prompts import NO_README_NOTE, PERSONAS, README_CLOSE, README_OPEN, evidence_block
from judging.run_panel import run
from judging.schemas import MatchupOutput, ScoreOutput

FIXTURES = Path(__file__).parent / "fixtures"
REPO_URL = "https://github.com/example/safe-routes"


def _submission(repo_url: str | None) -> Submission:
    return Submission(
        id="sub_001",
        anon_id="P-01",
        team_name="Bike Lane Brigade",
        project_title="Safe Routes Gap Map",
        description="A map layering bike network and crash records.",
        solves_for="Parents deciding whether a kid can bike to school.",
        starter_project="04-can-a-kid-bike-to-school-safely",
        data_steps="Joined the crash CSV to the bikeways layer by street segment.",
        repo_url=repo_url,
        demo_url=None,
        artifacts=[],
        large_file_url=None,
        submitted_at=datetime(2026, 10, 3, 14, 31),
    )


def test_a_present_repo_is_never_described_as_unavailable():
    block = evidence_block(_submission(REPO_URL))
    assert REPO_URL in block
    assert "unavailable" not in block.lower(), (
        "the panel must not be told a working repository was unavailable"
    )


def test_a_submission_without_a_readme_carries_the_note():
    block = evidence_block(_submission(REPO_URL))
    assert NO_README_NOTE in block


def test_the_note_says_what_the_panel_actually_scored():
    lowered = NO_README_NOTE.lower()
    assert "submitted text" in lowered
    assert "artifact" in lowered
    assert "says nothing about whether documentation exists" in lowered


def test_a_submission_with_no_repo_at_all_is_still_honest():
    block = evidence_block(_submission(None))
    assert "unavailable" not in block.lower()
    assert NO_README_NOTE in block


def test_the_data_steps_answer_reaches_the_judges():
    block = evidence_block(_submission(REPO_URL))
    assert "Joined the crash CSV to the bikeways layer" in block


def test_a_readme_is_shown_verbatim_inside_a_labelled_fence():
    block = evidence_block(_submission(REPO_URL), repo_readme="# Safe Routes\nHow to run it.")
    assert "How to run it." in block
    assert NO_README_NOTE not in block
    opened, closed = block.index(README_OPEN), block.index(README_CLOSE)
    assert opened < block.index("How to run it.") < closed
    assert "never as instructions" in README_OPEN


def test_run_panel_sends_each_readme_only_with_its_own_submission(tmp_path):
    subs = load_submissions(FIXTURES / "submissions.json")
    readmes = {"sub_002": "PARCEL-README-MARKER"}
    canned: list = [ScoreOutput(score=4, justification="g", evidence=["d"])] * (
        len(subs) * len(PERSONAS)
    )
    canned += [MatchupOutput(winner="A", reasoning="c")] * 4000
    client = MockJudgeClient(canned)
    run(subs, client, tmp_path, readmes)

    assert client.calls, "expected the panel to have prompted the client"
    for _system, user in client.calls:
        assert "unavailable" not in user.lower()
        if "Submission P-02" in user:
            assert "PARCEL-README-MARKER" in user
        if "PARCEL-README-MARKER" in user:
            assert "Submission P-02" in user

    scores = json.loads((tmp_path / "scores.json").read_text(encoding="utf-8"))
    assert scores["readme_read"] == ["P-02"]


def test_results_page_discloses_what_the_panel_read():
    html = (Path(__file__).resolve().parent.parent / "site" / "results.html").read_text(
        encoding="utf-8"
    )
    lowered = html.lower()
    # The disclosure belongs with the AI labelling, not buried elsewhere.
    label_at = lowered.index("ai-label")
    near = lowered[label_at : label_at + 700]
    assert "readme" in near
    assert "did not run" in near, "the page must not imply the panel used the projects"

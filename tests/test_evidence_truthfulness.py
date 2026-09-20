"""I8: the panel must not be told that a working repo is "unavailable".

evidence_block's `repo_readme` parameter is threaded through pass1 and pass2,
but run_panel never passes it -- no fetcher was built. So every judge read
"Repository: https://github.com/..." followed immediately by "(repository
unavailable or not provided)". The Craft and Continuation personas were being
told a team's working, documented repository was unavailable.

The plan descoped the fetcher on the grounds that §8's `reduced_evidence`
path covers it. `reduced_evidence` appears nowhere in the codebase (it is in
the §4.2 schema in the spec, not in judging/schemas.py), so nothing covered
it.

Owner decision: do not build a fetcher. Make the methodology truthful
instead.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from judging.client import MockJudgeClient
from judging.models import Submission, load_submissions
from judging.prompts import NO_REPO_FETCH_NOTE, evidence_block
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


def test_the_block_says_the_repository_was_not_fetched():
    block = evidence_block(_submission(REPO_URL))
    assert NO_REPO_FETCH_NOTE in block
    assert "not fetched" in NO_REPO_FETCH_NOTE.lower()


def test_the_note_says_what_the_panel_actually_scored():
    lowered = NO_REPO_FETCH_NOTE.lower()
    assert "submitted" in lowered
    assert "artifact" in lowered


def test_a_submission_with_no_repo_at_all_is_still_honest():
    block = evidence_block(_submission(None))
    assert "unavailable" not in block.lower()
    assert NO_REPO_FETCH_NOTE in block


def test_a_supplied_readme_is_used_verbatim_when_one_is_ever_passed():
    block = evidence_block(_submission(REPO_URL), repo_readme="# Safe Routes\nHow to run it.")
    assert "How to run it." in block
    assert NO_REPO_FETCH_NOTE not in block


def test_every_prompt_run_panel_actually_sends_carries_the_note(tmp_path):
    subs = load_submissions(FIXTURES / "submissions.json")
    canned: list = [ScoreOutput(score=4, justification="g", evidence=["d"])] * (len(subs) * 5)
    canned += [MatchupOutput(winner="A", reasoning="c")] * 4000
    client = MockJudgeClient(canned)
    run(subs, client, tmp_path)

    assert client.calls, "expected the panel to have prompted the client"
    for _system, user in client.calls:
        assert "unavailable" not in user.lower(), (
            "run_panel passes no README, so no prompt may claim a repo was unavailable"
        )
        assert NO_REPO_FETCH_NOTE in user


def test_results_page_discloses_that_repositories_were_not_fetched():
    html = (Path(__file__).resolve().parent.parent / "site" / "results.html").read_text(
        encoding="utf-8"
    )
    lowered = html.lower()
    assert "not fetched" in lowered or "did not fetch" in lowered, (
        "results.html must say what the panel actually read"
    )
    # The disclosure belongs with the AI labelling, not buried elsewhere.
    label_at = lowered.index("ai-label")
    assert "fetch" in lowered[label_at : label_at + 600]

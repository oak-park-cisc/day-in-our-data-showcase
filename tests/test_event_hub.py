"""The homepage and start guide keep the two-track promises (decision log #37)."""
from __future__ import annotations

import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"


def _text(name: str) -> str:
    return (SITE / name).read_text(encoding="utf-8")


def _flat(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).lower().split())


def test_entry_form_asks_how_the_data_became_the_result():
    html = _text("index.html")
    assert re.search(r'<textarea name="data_steps"[^>]*required', html)


def test_entry_form_field_names_match_what_the_sync_reads():
    """Renaming a field would silently drop it from submissions.json."""
    html = _text("index.html")
    for name in ["team_name", "project_title", "description", "solves_for", "data_steps",
                 "starter_project", "repo_url", "demo_url", "artifact", "large_file_url"]:
        assert f'name="{name}"' in html, name


def test_homepage_says_track_a_needs_no_github():
    flat = _flat(_text("index.html"))
    assert "no github account needed" in flat
    assert "civic spark" in flat


def test_homepage_says_the_vote_decides_and_the_panel_never_adds_to_it():
    flat = _flat(_text("index.html"))
    assert "how your entry is judged" in flat
    assert "never added to the vote" in flat


def test_homepage_welcomes_projects_without_ai():
    assert "no ai required" in _flat(_text("index.html"))


def test_start_guide_makes_github_a_track_b_prerequisite_only():
    flat = _flat(_text("start.html"))
    assert "track b only" in flat
    assert "no github account needed" in flat


def test_start_guide_gives_the_five_readme_headings():
    flat = _flat(_text("start.html"))
    for heading in ["the question", "the data", "how we got the numbers",
                    "how to use it", "status and next steps"]:
        assert heading in flat, heading

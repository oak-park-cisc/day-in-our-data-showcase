"""Cross-workflow invariants (spec 2026-09-24 §4.5–4.7).

1. Every bot commit carries [skip netlify]. Netlify's free plan allows ~20
   deploys a month and pauses the site at the cap; data commits must never
   spend one. Pages read data live from GitHub instead.
2. No workflow reads or stages data/ballots.json. Ballots live only in the
   tally's memory.

Text checks, no YAML parser (not a project dependency).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).resolve().parent.parent / ".github" / "workflows").glob("*.yml"))


def _commit_lines() -> list[tuple[str, str]]:
    found = []
    for wf in WORKFLOWS:
        for line in wf.read_text(encoding="utf-8").splitlines():
            if re.search(r"git commit\b", line):
                found.append((wf.name, line.strip()))
    return found


def test_the_three_data_workflows_commit():
    names = {name for name, _ in _commit_lines()}
    assert {"sync-submissions.yml", "judge.yml", "tally.yml"} <= names


@pytest.mark.parametrize("workflow,line", _commit_lines())
def test_every_bot_commit_skips_netlify(workflow, line):
    assert "[skip netlify]" in line, f"{workflow}: {line}"


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_no_workflow_touches_a_ballots_file(wf):
    assert "ballots.json" not in wf.read_text(encoding="utf-8")

"""Covering test for Finding 1 (coordinator review of task-16-report.md):
NETLIFY_SITE_ID was unreachable through the shipped workflow.

scripts/sync_netlify.py's resolve_form_id() and sync() read NETLIFY_SITE_ID
from the environment to disambiguate same-named forms across sites, but
.github/workflows/sync-submissions.yml's `env:` block only ever declared
NETLIFY_TOKEN. A GitHub Actions env var not listed under a step's `env:` is
invisible to that step's process no matter what secret exists -- so setting
the NETLIFY_SITE_ID secret, as the script's own error message told the
owner to do, would have changed nothing.

No YAML parser is used (PyYAML isn't a project dependency; this project
deliberately keeps its dependency list to anthropic+pydantic) -- a plain
line-range check between the step's `- name:` marker and the next step's
`- name:`/`- uses:` marker is enough and doesn't require parsing the whole
file's structure.
"""
from __future__ import annotations

from pathlib import Path

WORKFLOW_PATH = (
    Path(__file__).resolve().parent.parent / ".github" / "workflows" / "sync-submissions.yml"
)


def _sync_step_lines() -> list[str]:
    lines = WORKFLOW_PATH.read_text(encoding="utf-8").splitlines()
    start = next(
        i for i, line in enumerate(lines)
        if line.strip() == "- name: Sync submissions from Netlify Forms"
    )
    end = next(
        i for i in range(start + 1, len(lines))
        if lines[i].lstrip().startswith(("- name:", "- uses:"))
    )
    return lines[start:end]


def test_sync_step_declares_netlify_token():
    step = "\n".join(_sync_step_lines())
    assert "NETLIFY_TOKEN: ${{ secrets.NETLIFY_TOKEN }}" in step


def test_sync_step_declares_netlify_site_id_so_the_secret_is_reachable():
    """The actual regression: without this line, setting the NETLIFY_SITE_ID
    secret has zero effect, because GitHub Actions never exposes a secret to
    a step's environment unless that step's `env:` block names it."""
    step = "\n".join(_sync_step_lines())
    assert "NETLIFY_SITE_ID: ${{ secrets.NETLIFY_SITE_ID }}" in step


def test_sync_step_still_runs_the_script_with_data_dir():
    step = "\n".join(_sync_step_lines())
    assert "python scripts/sync_netlify.py --data-dir data" in step

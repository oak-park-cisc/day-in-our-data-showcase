"""The runbook is the owner's only script for event day; two of its steps
were wrong in ways no code test would catch (final whole-branch review).

1. The pre-event tally check must not spend a real slip code: tally.py keeps
   the first valid ballot per code, so the attendee later handed that slip
   would have their vote silently discarded, and the test pick would count.
2. The deploy-time snapshot is the fallback when GitHub rate-limits the
   library's shared IP. Unless a deploy happens after submissions close, that
   snapshot is the seeded empty list and the ballot page has nothing to offer.
"""
from __future__ import annotations

from pathlib import Path

RUNBOOK = (Path(__file__).resolve().parent.parent / "docs" / "deployment-runbook.md").read_text(
    encoding="utf-8"
)


def test_the_tally_check_does_not_spend_a_real_slip_code():
    assert "code from your slip sheet" not in RUNBOOK
    assert "not in `BALLOT_CODES`" in RUNBOOK


def test_test_entries_and_dry_run_results_are_cleaned_up_before_the_event():
    assert "Before the event: clean up" in RUNBOOK
    assert "data/results/" in RUNBOOK


def test_a_deploy_refreshes_the_snapshot_before_voting_opens():
    assert "before voting opens" in RUNBOOK

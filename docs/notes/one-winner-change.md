# One winner, no gift cards — implementation notes

**Date:** 2026-09-21
**Branch:** `fix/one-winner-no-gift-cards`

## What changed

The event's prizes changed. There are no gift cards. Every participant
receives a participation keychain, which is not rank-based — everyone gets
one regardless of how the vote goes. Every participating team (not only "the
top teams") is invited to share their build on the CISC website or at a CISC
meeting — the invitation widened rather than narrowed from the original event
program. One project wins the participant vote; per the owner, "the rankings
are really just for fun" below that line. If two projects tie for first,
both win — the page states a shared win, not an escalation.

## Code changes

- `voting/ranking.py`: `DEFAULT_AWARD_COUNT` is now `1` (was `3`), still an
  overridable parameter, not a hardcoded literal. Module docstring rewritten
  to explain the one-winner rule and why the tie-boundary machinery is kept:
  at `award_count = 1`, "does this tied group straddle the award cut"
  collapses to exactly "is this a tie for first place."
- `voting/compare.py`: docstring wording updated ("gift cards" → "projects
  win"); no behavior change — `award_count` still flows through from
  `DEFAULT_AWARD_COUNT`.
- `site/scripts/results.js`: the boundary-tie notice now reads as a shared
  win ("It's a tie for first place — and that means a shared win.") instead
  of naming a gift-card boundary and CISC. The rendering mechanism
  (`comparison.award_boundary_tie` / `award_boundary_tie_ids`) is unchanged.
- `.github/workflows/tally.yml`: comment updated to describe the new
  semantics; no logic change (still calls `ranking_summary(result.counts)`
  with the default `award_count`).
- `site/results.html`, `site/vote.html`: "The participant vote decides the
  awards" → "the winner", in all four places (meta description and body copy
  on both pages). The panel-decides-nothing contrast is preserved verbatim.

## Spec and docs

- `docs/superpowers/specs/2026-09-19-day-in-our-data-showcase-design.md`
  gained a new §1.2, "Amendment (2026-09-21) — prizes changed," and a dated
  amendment note appended after the original §6.3 paragraph. The original
  §1.1 quote and §6.3 CISC-decides text are left intact above both, as the
  record of what participants were told at registration.
- `docs/deployment-runbook.md`: the closing "gift-card count" paragraph
  rewritten to describe the one-winner rule and point at the spec amendment.
- `docs/decision-log.md`: entry **34** added, recording the change and its
  reasoning, cross-referenced against entries #26/#27/#32/#33.

## Tests

Existing tie tests (encoding three gift cards and third-place boundary
positions) were moved to the new rule, not deleted:

- `tests/test_ranking.py`: added `test_default_award_count_is_one`,
  `test_tie_for_first_is_flagged_as_the_award_boundary_at_the_default_count`,
  `test_tie_for_third_is_not_flagged_at_the_default_count`. The generic
  competition-ranking and tie-group tests are unchanged. The former
  boundary tests at explicit `award_count=3` (straddling/inside/outside)
  are kept, renamed to make clear they demonstrate the override mechanism
  rather than the default.
- `tests/test_compare_ranking.py`: added a first-place-tie fixture to cover
  the new default behavior; kept an explicit `award_count=3` override test
  to prove the constant isn't hardcoded downstream.
- `tests/test_tally_workflow.py`: the existing "three-way tie for
  second/third/fourth" fixture now asserts `award_boundary_tie is False`
  (it no longer touches the one-winner cut) instead of `True`. Added a new
  fixture/test for a tie at first place through the real workflow script,
  asserting `award_boundary_tie is True` with the tied ids.
- `tests/js/results.ties.test.js`: added tests asserting the page states a
  shared win for a tie at first, and that the old "CISC decides" / gift-card
  wording is gone. Existing rank-sharing and escaping tests kept, with
  wording in comments updated.

Every property the old tests asserted still holds: equal counts share a
rank, higher counts rank strictly better, the boundary flag fires exactly
when a tie straddles the winning cut (now a tie for first) and not when a
tie is wholly inside or outside it, and an explicit `award_count` override
still works end to end.

## Verification

- `python -m pytest tests/ -q` → 178 passed.
- `node --test tests/js/*.test.js` → 22 passed, 1 pre-existing skip (smoke
  test against locally generated mock panel output, unrelated to this
  change — it skips whenever `site/data/` hasn't been generated locally).

## Note on scope

Per the coordinator, no participant-facing copy about the "every team is
invited to share their build" clarification was added to the site — that is
being settled with the owner separately. This change is confined to the
spec amendment and the decision log.

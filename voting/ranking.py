"""Tie-aware ranking of approval counts, for display and for the winner call.

Spec 6.3 (amended 2026-09-21) is explicit, and this module exists because the
obvious one-liner (``sorted(counts, key=lambda s: (-counts[s], s))``) quietly
violates it:

    "Because picks are unranked, there is no principled way to break a tie in
    approval count from the ballot data - so the tally does not invent one.
    Tied projects share a rank and are displayed as tied. A tie for first
    place is a shared win: both projects win, and the page says so."

Sorting by ``(-count, id)`` ranks two equal-vote projects by submission id -
that is, by which team happened to file first - and then the page renders the
result as a hard ordinal. That is an invented tiebreak wearing the costume of
a result.

Ties are derived from ``voting.stats.average_ranks``, the tie-aware ranking
the project already had (it is what makes ``spearman`` correct in the presence
of ties). ``average_ranks`` gives tied entries a shared *fractional* rank
(two projects tied for 3rd both get 3.5), which is right for correlation and
wrong for a table of results, so ``competition_ranks`` converts each shared
group to standard competition ranking ("1224"): every member of a tied group
takes the best position the group spans, and the positions the group consumed
are skipped. Equal average rank <=> tied is the single source of truth for
"are these two tied", so display and statistics can never disagree.

AWARD COUNT. There are no gift cards and no ranked prize tiers: one project
wins, full stop, and (per the owner) "the rankings are really just for fun"
below that line. The boundary machinery from the original multi-winner design
still does real work, though - with one winner, "does this tied group
straddle the award cut" collapses to exactly "is this a tie for first place",
which is the one case that still needs a rule: both projects share the win
rather than the vote inventing a tiebreak. So the cut stays a parameter,
defaulting to DEFAULT_AWARD_COUNT below, rather than a hardcoded 1 - nothing
else in the codebase should assume the number, in case that ever changes
again.
"""
from __future__ import annotations

from voting.stats import average_ranks

#: How many projects win. One - see the module docstring. Kept as an
#: overridable constant, not a hardcoded literal, so downstream callers
#: (build_comparison, tests) can still pass a different cut explicitly.
DEFAULT_AWARD_COUNT = 1


def _groups(counts: dict[str, int]) -> list[list[str]]:
    """Projects grouped by shared approval count, best group first.

    Within a group the ids are sorted only so the output is deterministic;
    that order carries no meaning and must never be rendered as a ranking.
    """
    if not counts:
        return []
    shared = average_ranks(counts)  # tied entries share one fractional rank
    by_rank: dict[float, list[str]] = {}
    for key, rank in shared.items():
        by_rank.setdefault(rank, []).append(key)
    return [sorted(by_rank[rank]) for rank in sorted(by_rank)]


def competition_ranks(counts: dict[str, int]) -> dict[str, int]:
    """Standard competition ranking: tied projects share the best rank they span.

    {a: 9, b: 5, c: 5, d: 2} -> {a: 1, b: 2, c: 2, d: 4}. Rank 3 is skipped
    because b and c between them consumed positions 2 and 3.
    """
    ranks: dict[str, int] = {}
    position = 1
    for group in _groups(counts):
        for key in group:
            ranks[key] = position
        position += len(group)
    return ranks


def tie_groups(counts: dict[str, int]) -> list[list[str]]:
    """Only the genuine ties (groups of two or more), best-placed group first."""
    return [group for group in _groups(counts) if len(group) > 1]


def ranking_summary(
    counts: dict[str, int], award_count: int = DEFAULT_AWARD_COUNT
) -> dict:
    """Everything the page and `vote.json` need to show a tie as a tie.

    ``ranking`` is a flat display order (best count first, ids only to keep
    the output stable). It is deliberately NOT the thing that decides who
    placed where: ``ranks`` is, and a renderer must read ``ranks`` for the
    "#" column or it will re-invent the ordinals this module exists to
    prevent.

    ``award_boundary_tie`` is true when a tied group straddles the winning
    cut - some of its members inside the award set, some outside. At
    ``award_count = 1`` that is exactly a tie for first place: both members
    win, and there is nothing to escalate.
    """
    groups = _groups(counts)
    ranks = competition_ranks(counts)

    boundary_ids: list[str] = []
    position = 1
    for group in groups:
        first, last = position, position + len(group) - 1
        # Straddles the cut iff the group starts at or above the boundary and
        # ends below it. A group entirely inside the award set, or entirely
        # outside it, needs no decision.
        if len(group) > 1 and first <= award_count < last + 1 and last > award_count:
            boundary_ids = list(group)
        position += len(group)

    return {
        "ranking": [key for group in groups for key in group],
        "ranks": ranks,
        "ties": tie_groups(counts),
        "award_count": award_count,
        "award_boundary_tie": bool(boundary_ids),
        "award_boundary_tie_ids": boundary_ids,
    }

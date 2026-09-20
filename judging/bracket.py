from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

CIVIC = "civic-impact"
INTEGRITY = "data-integrity"


@dataclass(frozen=True)
class SeedEntry:
    anon_id: str
    scores: dict[str, int]
    submitted_at: datetime


@dataclass(frozen=True)
class Pairing:
    a: str
    b: str | None  # None means a bye


@dataclass(frozen=True)
class Vote:
    persona: str
    winner: str
    swap_confirmed: bool


def mean_score(scores: dict[str, int]) -> float:
    return sum(scores.values()) / len(scores)


def seed_entries(entries: list[SeedEntry]) -> list[SeedEntry]:
    """Highest mean first. Ties: civic impact, then data integrity, then earliest submission."""
    return sorted(
        entries,
        key=lambda e: (
            -mean_score(e.scores),
            -e.scores[CIVIC],
            -e.scores[INTEGRITY],
            e.submitted_at,
        ),
    )


def bracket_slots(size: int) -> list[int]:
    """Standard tournament seeding order: 1 plays the lowest seed, favourites meet last."""
    slots = [1]
    while len(slots) < size:
        n = len(slots) * 2
        slots = [s for pair in ((x, n + 1 - x) for x in slots) for s in pair]
    return slots


def _bracket_size(n: int) -> int:
    size = 1
    while size < n:
        size *= 2
    return size


def build_rounds(seeded: list[SeedEntry]) -> list[list[Pairing]]:
    """Round one only; later rounds depend on results and are built as they resolve."""
    if len(seeded) == 0:
        return [[]]

    size = _bracket_size(len(seeded))
    by_seed = {i + 1: e.anon_id for i, e in enumerate(seeded)}
    ordered = [by_seed.get(s) for s in bracket_slots(size)]
    first: list[Pairing] = []

    if size == 1:
        first.append(Pairing(a=ordered[0], b=None))
        return [first]

    for i in range(0, size, 2):
        a, b = ordered[i], ordered[i + 1]
        if a is None:
            a, b = b, None
        first.append(Pairing(a=a, b=b))
    return [first]


def resolve(votes: list[Vote], a: str, b: str, seed_of: dict[str, int]) -> str:
    """Majority of votes that survived the position swap. Any tie advances the higher seed."""
    higher = a if seed_of[a] < seed_of[b] else b
    counted = Counter(v.winner for v in votes if v.swap_confirmed)
    if not counted:
        return higher
    top = counted.most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        return higher
    return top[0][0]


def finish_order(
    rounds: list[list[dict]],
    seed_of: dict[str, int],
    champion: str | None,
) -> list[str]:
    """Rank entrants by how far they got in the bracket, best first.

    Single elimination produces only a partial order -- everyone knocked out
    in the same round is, strictly speaking, incomparable -- so a total order
    has to be *chosen*. The rule here is the conventional tournament one, and
    it is stated in advance rather than falling out of list order:

        1. The champion.
        2. Then everyone else by the round they were eliminated in, latest
           round first (so the losing finalist is runner-up).
        3. Within one round, the better seed places higher.
        4. Anyone who never appeared in a played matchup trails, by seed.

    Rule 3 is the only judgement call: seed comes from pass-1 mean score, so
    the tiebreak is the panel's own prior, not who submitted first. Byes are
    not eliminations -- a bye advances, it does not knock anybody out.

    `rounds` is run_panel's `rounds_out` shape: a list per round of dicts with
    "a", "b" (None for a bye) and "winner".
    """
    eliminated_in: dict[str, int] = {}
    for index, played in enumerate(rounds):
        for matchup in played:
            a, b = matchup.get("a"), matchup.get("b")
            if b is None or matchup.get("bye"):
                continue
            loser = a if matchup.get("winner") == b else b
            if loser is not None:
                eliminated_in[loser] = index + 1

    def by_seed(anon_id: str) -> int:
        # An entrant missing from seed_of sorts last rather than raising:
        # a ranking is not worth crashing the whole publish over.
        return seed_of.get(anon_id, len(seed_of) + 1)

    order: list[str] = []
    if champion is not None:
        order.append(champion)

    losers = [a for a in eliminated_in if a != champion]
    order += sorted(losers, key=lambda a: (-eliminated_in[a], by_seed(a)))

    placed = set(order)
    order += sorted((a for a in seed_of if a not in placed), key=by_seed)
    return order

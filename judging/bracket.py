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
    size = _bracket_size(len(seeded))
    by_seed = {i + 1: e.anon_id for i, e in enumerate(seeded)}
    ordered = [by_seed.get(s) for s in bracket_slots(size)]
    first: list[Pairing] = []
    for i in range(0, size, 2):
        a, b = ordered[i], ordered[i + 1]
        if a is None and b is None:
            continue
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

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

TURNOUT_FLOOR = 10
PICKS_PER_BALLOT = 3


@dataclass(frozen=True)
class Ballot:
    code: str
    picks: list[str]
    cast_at: datetime


@dataclass
class TallyResult:
    counts: dict[str, int]
    valid: int
    invalid: int
    indicative: bool


def tally(
    ballots: list[Ballot],
    valid_codes: set[str],
    known_ids: set[str],
    floor: int = TURNOUT_FLOOR,
) -> TallyResult:
    """Count votes per project and validate ballots.

    Ballots are processed in timestamp order. For each code, the first VALID
    ballot is counted; any subsequent ballot with the same code (valid or not)
    is rejected. This means a voter whose first attempt is malformed (e.g.,
    duplicate picks) does not forfeit their right to vote — a second valid
    attempt on the same code will be counted instead.

    Returns TallyResult with vote counts, valid/invalid ballot counts, and an
    indicative flag (True if valid votes < floor, indicating insufficient
    sample size for statistical confidence).
    """
    counts: Counter[str] = Counter({pid: 0 for pid in known_ids})
    seen: set[str] = set()
    valid = invalid = 0

    for b in sorted(ballots, key=lambda x: x.cast_at):
        if b.code not in valid_codes or b.code in seen:
            invalid += 1
            continue
        if len(b.picks) != PICKS_PER_BALLOT or len(set(b.picks)) != PICKS_PER_BALLOT:
            invalid += 1
            continue
        if any(p not in known_ids for p in b.picks):
            invalid += 1
            continue
        seen.add(b.code)
        counts.update(b.picks)
        valid += 1

    return TallyResult(
        counts=dict(counts), valid=valid, invalid=invalid, indicative=valid < floor
    )

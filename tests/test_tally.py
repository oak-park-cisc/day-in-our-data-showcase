from datetime import datetime, timezone

from voting.tally import Ballot, tally

KNOWN = {"sub_001", "sub_002", "sub_003", "sub_004"}
CODES = {f"CODE{i:03d}" for i in range(1, 21)}


def ballot(code: str, picks: list[str], minute: int = 0) -> Ballot:
    return Ballot(
        code=code, picks=picks,
        cast_at=datetime(2026, 10, 5, 12, minute, tzinfo=timezone.utc),
    )


def valid_set(n: int) -> list[Ballot]:
    return [ballot(f"CODE{i:03d}", ["sub_001", "sub_002", "sub_003"], i) for i in range(1, n + 1)]


def test_counts_each_pick_once_per_ballot():
    result = tally(valid_set(10), CODES, KNOWN)
    assert result.counts["sub_001"] == 10
    assert result.counts["sub_004"] == 0
    assert result.valid == 10


def test_unknown_code_is_invalid():
    result = tally(valid_set(10) + [ballot("NOTACODE", ["sub_001", "sub_002", "sub_003"], 30)], CODES, KNOWN)
    assert result.valid == 10
    assert result.invalid == 1


def test_reused_code_keeps_only_the_first_ballot():
    ballots = valid_set(10) + [ballot("CODE001", ["sub_004", "sub_002", "sub_003"], 40)]
    result = tally(ballots, CODES, KNOWN)
    assert result.valid == 10
    assert result.counts["sub_004"] == 0


def test_unknown_project_invalidates_the_whole_ballot():
    ballots = valid_set(10) + [ballot("CODE011", ["sub_001", "sub_999", "sub_003"], 50)]
    result = tally(ballots, CODES, KNOWN)
    assert result.valid == 10
    assert result.invalid == 1


def test_duplicate_picks_invalidate_the_ballot():
    """Spec amendment 2: three picks must be distinct, or one voter triples a count."""
    ballots = valid_set(10) + [ballot("CODE011", ["sub_001", "sub_001", "sub_002"], 55)]
    result = tally(ballots, CODES, KNOWN)
    assert result.valid == 10
    assert result.invalid == 1
    assert result.counts["sub_001"] == 10


def test_below_floor_turnout_is_marked_indicative():
    result = tally(valid_set(9), CODES, KNOWN)
    assert result.indicative is True


def test_at_floor_turnout_is_not_indicative():
    result = tally(valid_set(10), CODES, KNOWN)
    assert result.indicative is False


def test_codes_are_absent_from_the_result():
    result = tally(valid_set(10), CODES, KNOWN)
    assert "CODE001" not in repr(result)


def test_first_invalid_ballot_does_not_forfeit_the_vote():
    """An invalid first ballot on a code does not prevent a valid second ballot.

    The deduplication rule keeps only the first VALID ballot per code, so a
    voter whose first attempt has duplicate picks can correct it with a second
    attempt on the same code and have the second (valid) ballot counted.
    """
    ballots = valid_set(10) + [
        ballot("CODE011", ["sub_001", "sub_001", "sub_002"], 40),  # invalid: duplicate picks
        ballot("CODE011", ["sub_001", "sub_002", "sub_003"], 41),  # valid: second attempt
    ]
    result = tally(ballots, CODES, KNOWN)
    assert result.valid == 11
    assert result.invalid == 1
    assert result.counts["sub_001"] == 11
    assert result.counts["sub_002"] == 11
    assert result.counts["sub_003"] == 11

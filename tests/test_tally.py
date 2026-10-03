from datetime import datetime, timezone

from voting.tally import Ballot, tally

KNOWN = {"sub_001", "sub_002", "sub_003", "sub_004"}


def ballot(voter: str, picks: list[str], minute: int = 0) -> Ballot:
    return Ballot(
        voter=voter, picks=picks,
        cast_at=datetime(2026, 10, 5, 12, minute, tzinfo=timezone.utc),
    )


def valid_set(n: int) -> list[Ballot]:
    return [ballot(f"DEV{i:03d}", ["sub_001", "sub_002", "sub_003"], i) for i in range(1, n + 1)]


def test_counts_each_pick_once_per_ballot():
    result = tally(valid_set(10), KNOWN)
    assert result.counts["sub_001"] == 10
    assert result.counts["sub_004"] == 0
    assert result.valid == 10


def test_ballot_without_a_device_id_is_invalid():
    result = tally(valid_set(10) + [ballot("", ["sub_001", "sub_002", "sub_003"], 30)], KNOWN)
    assert result.valid == 10
    assert result.invalid == 1


def test_second_ballot_from_a_device_is_not_counted():
    ballots = valid_set(10) + [ballot("DEV001", ["sub_004", "sub_002", "sub_003"], 40)]
    result = tally(ballots, KNOWN)
    assert result.valid == 10
    assert result.counts["sub_004"] == 0


def test_unknown_project_invalidates_the_whole_ballot():
    ballots = valid_set(10) + [ballot("DEV011", ["sub_001", "sub_999", "sub_003"], 50)]
    result = tally(ballots, KNOWN)
    assert result.valid == 10
    assert result.invalid == 1


def test_duplicate_picks_invalidate_the_ballot():
    """Spec amendment 2: three picks must be distinct, or one voter triples a count."""
    ballots = valid_set(10) + [ballot("DEV011", ["sub_001", "sub_001", "sub_002"], 55)]
    result = tally(ballots, KNOWN)
    assert result.valid == 10
    assert result.invalid == 1
    assert result.counts["sub_001"] == 10


def test_below_floor_turnout_is_marked_indicative():
    result = tally(valid_set(9), KNOWN)
    assert result.indicative is True


def test_at_floor_turnout_is_not_indicative():
    result = tally(valid_set(10), KNOWN)
    assert result.indicative is False


def test_device_ids_are_absent_from_the_result():
    result = tally(valid_set(10), KNOWN)
    assert "DEV001" not in repr(result)


def test_first_invalid_ballot_does_not_forfeit_the_vote():
    """An invalid first ballot from a device does not prevent a valid second one.

    The deduplication rule keeps only the first VALID ballot per device, so a
    voter whose first attempt has duplicate picks can correct it and have the
    second (valid) ballot counted.
    """
    ballots = valid_set(10) + [
        ballot("DEV011", ["sub_001", "sub_001", "sub_002"], 40),  # invalid: duplicate picks
        ballot("DEV011", ["sub_001", "sub_002", "sub_003"], 41),  # valid: second attempt
    ]
    result = tally(ballots, KNOWN)
    assert result.valid == 11
    assert result.invalid == 1
    assert result.counts["sub_001"] == 11
    assert result.counts["sub_002"] == 11
    assert result.counts["sub_003"] == 11

from datetime import datetime, timezone

import pytest

from judging.bracket import (
    Pairing, SeedEntry, Vote, bracket_slots, build_rounds, mean_score, resolve, seed_entries,
)

PERSONAS = ["civic-impact", "data-integrity", "usability-access", "craft", "continuation"]


def entry(anon_id: str, scores: list[int], minute: int = 0) -> SeedEntry:
    return SeedEntry(
        anon_id=anon_id,
        scores=dict(zip(PERSONAS, scores)),
        submitted_at=datetime(2026, 10, 3, 14, minute, tzinfo=timezone.utc),
    )


def test_mean_score():
    assert mean_score({"a": 4, "b": 5, "c": 3}) == 4.0


def test_seeding_orders_by_mean_descending():
    ordered = seed_entries([entry("P-01", [3, 3, 3, 3, 3]), entry("P-02", [5, 5, 5, 5, 5])])
    assert [e.anon_id for e in ordered] == ["P-02", "P-01"]


def test_seeding_tie_breaks_on_civic_impact_then_data_integrity():
    # identical means of 3.0; P-02 wins on civic impact
    a = entry("P-01", [2, 4, 3, 3, 3])
    b = entry("P-02", [4, 2, 3, 3, 3])
    assert [e.anon_id for e in seed_entries([a, b])] == ["P-02", "P-01"]


def test_seeding_final_tie_breaks_on_earlier_submission():
    a = entry("P-01", [3, 3, 3, 3, 3], minute=50)
    b = entry("P-02", [3, 3, 3, 3, 3], minute=10)
    assert [e.anon_id for e in seed_entries([a, b])] == ["P-02", "P-01"]


@pytest.mark.parametrize(
    "size,expected",
    [(2, [1, 2]), (4, [1, 4, 2, 3]), (8, [1, 8, 4, 5, 2, 7, 3, 6])],
)
def test_bracket_slots_are_standard_seeding_order(size, expected):
    assert bracket_slots(size) == expected


def test_six_entries_give_top_two_seeds_byes():
    seeded = seed_entries([entry(f"P-0{i}", [6 - i] * 5) for i in range(1, 7)])
    rounds = build_rounds(seeded)
    first = rounds[0]
    byes = [p for p in first if p.b is None]
    assert len(byes) == 2
    assert {p.a for p in byes} == {"P-01", "P-02"}


def test_majority_of_surviving_votes_wins():
    votes = [
        Vote("civic-impact", "P-01", True), Vote("data-integrity", "P-01", True),
        Vote("usability-access", "P-02", True), Vote("craft", "P-02", True),
        Vote("continuation", "P-01", True),
    ]
    assert resolve(votes, "P-01", "P-02", {"P-01": 1, "P-02": 2}) == "P-01"


def test_votes_that_flip_under_swap_do_not_count():
    votes = [
        Vote("civic-impact", "P-02", False), Vote("data-integrity", "P-02", False),
        Vote("usability-access", "P-02", False), Vote("craft", "P-01", True),
        Vote("continuation", "P-01", True),
    ]
    # three unconfirmed votes are discarded; P-01 wins 2-0
    assert resolve(votes, "P-01", "P-02", {"P-01": 1, "P-02": 2}) == "P-01"


def test_all_abstentions_advance_the_higher_seed():
    votes = [Vote(p, "P-02", False) for p in PERSONAS]
    assert resolve(votes, "P-01", "P-02", {"P-01": 1, "P-02": 2}) == "P-01"


def test_even_split_advances_the_higher_seed():
    """Spec amendment 1: a 2-2 tie after abstentions goes to the higher seed."""
    votes = [
        Vote("civic-impact", "P-01", True), Vote("data-integrity", "P-01", True),
        Vote("usability-access", "P-02", True), Vote("craft", "P-02", True),
        Vote("continuation", "P-02", False),
    ]
    assert resolve(votes, "P-01", "P-02", {"P-01": 1, "P-02": 2}) == "P-01"

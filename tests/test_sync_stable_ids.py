"""I5: public ids must be stable across syncs.

build_submissions sorted by created_at and assigned sub_{i+1:03d} /
P-{i+1:02d} by index. Ballots store picks as the public ids captured at vote
time, and spec §2.1 puts deleting a submission in scope as an admin action --
which a public civic form guarantees will be used, because spam arrives. The
moment one submission is removed, every later submission shifts down and every
ballot naming sub_005 silently counts for a different project. No error, no
test, wrong awards.

Netlify submissions carry their own stable `id`. The mapping from that id to
the public number is committed (data/id_map.json) and only ever grows.

The fake get_json here ignores query strings so these tests do not care
whether the fetch is paginated.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "sync_netlify.py"
spec = importlib.util.spec_from_file_location("sync_netlify_ids", SCRIPT_PATH)
sync_netlify = importlib.util.module_from_spec(spec)
sys.modules["sync_netlify_ids"] = sync_netlify
spec.loader.exec_module(sync_netlify)  # type: ignore[union-attr]

FORMS = [
    {"id": "form-sub", "name": "submission", "site_id": "site-abc"},
    {"id": "form-ballot", "name": "ballot", "site_id": "site-abc"},
]


def _submission(netlify_id: str, minute: int, title: str) -> dict:
    return {
        "id": netlify_id,
        "form_id": "form-sub",
        "created_at": f"2026-10-03T14:{minute:02d}:00.000Z",
        "data": {"team_name": f"Team {title}", "project_title": title},
    }


FIRST_SYNC = [
    _submission("nl-a", 31, "Alpha"),
    _submission("nl-b", 40, "Beta"),
    _submission("nl-c", 50, "Gamma"),
    _submission("nl-d", 55, "Delta"),
]


def _fake_get_json(submissions: list[dict], ballots: list[dict] | None = None):
    """Route by path only, so pagination query strings are irrelevant here."""
    def _get(url: str, token: str, **kwargs):
        path = urlsplit(url).path
        if path.endswith("/forms"):
            return FORMS
        if "form-sub" in path:
            return submissions
        if "form-ballot" in path:
            return ballots or []
        raise AssertionError(f"unexpected URL: {url}")

    return _get


def _sync(data_dir: Path, submissions: list[dict]) -> list[dict]:
    sync_netlify.sync(
        "test-token", data_dir, site_id=None, get_json=_fake_get_json(submissions)
    )
    return json.loads((data_dir / "submissions.json").read_text(encoding="utf-8"))


def _public_ids(records: list[dict]) -> dict[str, str]:
    """project_title -> public id, so the assertion reads in human terms."""
    return {r["project_title"]: r["id"] for r in records}


def test_first_sync_numbers_by_submitted_at(tmp_path):
    records = _sync(tmp_path, FIRST_SYNC)
    assert [r["id"] for r in records] == ["sub_001", "sub_002", "sub_003", "sub_004"]
    assert [r["anon_id"] for r in records] == ["P-01", "P-02", "P-03", "P-04"]


def test_deleting_a_middle_submission_does_not_renumber_the_survivors(tmp_path):
    before = _public_ids(_sync(tmp_path, FIRST_SYNC))
    assert before == {
        "Alpha": "sub_001", "Beta": "sub_002", "Gamma": "sub_003", "Delta": "sub_004"
    }

    # An admin deletes Beta (spam, a duplicate, a withdrawal -- it does not
    # matter which). Every ballot already cast names sub_003 for Gamma.
    survivors = [s for s in FIRST_SYNC if s["id"] != "nl-b"]
    after = _public_ids(_sync(tmp_path, survivors))

    assert after == {"Alpha": "sub_001", "Gamma": "sub_003", "Delta": "sub_004"}, (
        "surviving submissions must keep the public ids ballots were cast against"
    )


def test_anon_ids_stay_in_lockstep_with_public_ids_after_a_deletion(tmp_path):
    _sync(tmp_path, FIRST_SYNC)
    survivors = [s for s in FIRST_SYNC if s["id"] != "nl-b"]
    records = _sync(tmp_path, survivors)
    for record in records:
        assert record["anon_id"] == "P-" + record["id"].removeprefix("sub_").lstrip("0").zfill(2)


def test_a_deleted_number_is_never_reissued_to_a_new_submission(tmp_path):
    _sync(tmp_path, FIRST_SYNC)
    survivors = [s for s in FIRST_SYNC if s["id"] != "nl-b"]
    _sync(tmp_path, survivors)

    # A new team files after the deletion. It must NOT inherit sub_002.
    later = survivors + [_submission("nl-e", 59, "Epsilon")]
    records = _public_ids(_sync(tmp_path, later))
    assert records["Epsilon"] == "sub_005"
    assert "sub_002" not in records.values()


def test_a_restored_submission_gets_its_original_number_back(tmp_path):
    _sync(tmp_path, FIRST_SYNC)
    survivors = [s for s in FIRST_SYNC if s["id"] != "nl-b"]
    _sync(tmp_path, survivors)
    records = _public_ids(_sync(tmp_path, FIRST_SYNC))
    assert records["Beta"] == "sub_002"


def test_a_backdated_submission_takes_the_next_free_number(tmp_path):
    # Netlify can surface a submission late. It must not claim a number an
    # earlier sync already handed out just because its created_at is older.
    _sync(tmp_path, FIRST_SYNC)
    late = FIRST_SYNC + [_submission("nl-z", 35, "Zeta")]
    records = _public_ids(_sync(tmp_path, late))
    assert records["Zeta"] == "sub_005"
    assert records["Beta"] == "sub_002"


def test_the_map_is_committed_and_keeps_deleted_entries(tmp_path):
    _sync(tmp_path, FIRST_SYNC)
    survivors = [s for s in FIRST_SYNC if s["id"] != "nl-b"]
    _sync(tmp_path, survivors)

    mapping = json.loads((tmp_path / "id_map.json").read_text(encoding="utf-8"))
    assert mapping["nl-b"] == 2, "the map must not forget a number it has issued"
    assert mapping["nl-d"] == 4


def test_a_submission_without_a_netlify_id_aborts_rather_than_guessing(tmp_path):
    broken = FIRST_SYNC + [{"form_id": "form-sub", "created_at": "2026-10-03T15:00:00.000Z", "data": {}}]
    with pytest.raises(sync_netlify.NetlifySyncError):
        _sync(tmp_path, broken)
    assert not (tmp_path / "submissions.json").exists()


def test_a_corrupt_map_aborts_rather_than_silently_renumbering(tmp_path):
    _sync(tmp_path, FIRST_SYNC)
    (tmp_path / "id_map.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(sync_netlify.NetlifySyncError):
        _sync(tmp_path, FIRST_SYNC)

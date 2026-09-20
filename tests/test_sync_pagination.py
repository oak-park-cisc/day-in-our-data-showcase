"""I6: GET /forms/{id}/submissions is paged.

The script treated the first response as the whole set. Netlify pages at 100
per request by default, so past 100 cast ballots the tally would silently
count a subset and publish it as the residents' verdict.

The contract these tests pin: every page is fetched before anything is
written, a short page ends the loop, and any failed page aborts the whole
sync rather than committing a partial set.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "sync_netlify.py"
spec = importlib.util.spec_from_file_location("sync_netlify_pages", SCRIPT_PATH)
sync_netlify = importlib.util.module_from_spec(spec)
sys.modules["sync_netlify_pages"] = sync_netlify
spec.loader.exec_module(sync_netlify)  # type: ignore[union-attr]

FORMS = [
    {"id": "form-sub", "name": "submission", "site_id": "site-abc"},
    {"id": "form-ballot", "name": "ballot", "site_id": "site-abc"},
]


def _submission(n: int) -> dict:
    return {
        "id": f"nl-s-{n:04d}",
        "created_at": f"2026-10-03T14:00:{n % 60:02d}.{n:04d}Z",
        "data": {"team_name": f"Team {n}", "project_title": f"Project {n}"},
    }


def _ballot(n: int) -> dict:
    return {
        "id": f"nl-b-{n:04d}",
        "created_at": f"2026-10-03T16:00:{n % 60:02d}.{n:04d}Z",
        "data": {"code": f"CODE{n:04d}", "pick_1": "sub_001", "pick_2": "sub_002", "pick_3": "sub_003"},
    }


class _PagingApi:
    """Serves a list in pages of `page_size`, recording every page requested."""

    def __init__(self, submissions: list[dict], ballots: list[dict], page_size: int = 100):
        self.submissions = submissions
        self.ballots = ballots
        self.page_size = page_size
        self.requests: list[tuple[str, int]] = []
        self.fail_on: tuple[str, int] | None = None

    def __call__(self, url: str, token: str, **kwargs):
        parts = urlsplit(url)
        if parts.path.endswith("/forms"):
            return FORMS
        query = parse_qs(parts.query)
        page = int(query.get("page", ["1"])[0])
        per_page = int(query.get("per_page", [str(self.page_size)])[0])
        which = "submissions" if "form-sub" in parts.path else "ballots"
        self.requests.append((which, page))
        if self.fail_on == (which, page):
            raise sync_netlify.NetlifySyncError(f"Netlify API GET {url} returned HTTP 500")
        source = self.submissions if which == "submissions" else self.ballots
        size = min(per_page, self.page_size)
        start = (page - 1) * size
        return source[start : start + size]


def test_every_page_of_submissions_is_fetched(tmp_path):
    api = _PagingApi([_submission(n) for n in range(1, 251)], [])
    sync_netlify.sync("test-token", tmp_path, site_id=None, get_json=api)

    records = json.loads((tmp_path / "submissions.json").read_text(encoding="utf-8"))
    assert len(records) == 250
    assert [p for kind, p in api.requests if kind == "submissions"] == [1, 2, 3]


def test_every_page_of_ballots_is_fetched(tmp_path):
    api = _PagingApi([_submission(1)], [_ballot(n) for n in range(1, 151)])
    sync_netlify.sync("test-token", tmp_path, site_id=None, get_json=api)

    ballots = json.loads((tmp_path / "ballots.json").read_text(encoding="utf-8"))
    assert len(ballots) == 150
    assert len({b["code_hash"] for b in ballots}) == 150


def test_an_exactly_full_page_still_asks_for_the_next_one(tmp_path):
    # 100 records is indistinguishable from "a full page with more behind it"
    # without asking, so the loop must ask and only stop on the short page.
    api = _PagingApi([_submission(n) for n in range(1, 101)], [])
    sync_netlify.sync("test-token", tmp_path, site_id=None, get_json=api)
    assert [p for kind, p in api.requests if kind == "submissions"] == [1, 2]
    assert len(json.loads((tmp_path / "submissions.json").read_text(encoding="utf-8"))) == 100


def test_a_short_first_page_stops_after_one_request(tmp_path):
    api = _PagingApi([_submission(n) for n in range(1, 15)], [])
    sync_netlify.sync("test-token", tmp_path, site_id=None, get_json=api)
    assert [p for kind, p in api.requests if kind == "submissions"] == [1]


def test_an_empty_form_stops_after_one_request(tmp_path):
    api = _PagingApi([], [])
    sync_netlify.sync("test-token", tmp_path, site_id=None, get_json=api)
    assert api.requests == [("submissions", 1), ("ballots", 1)]
    assert json.loads((tmp_path / "submissions.json").read_text(encoding="utf-8")) == []


def test_a_failed_later_page_aborts_the_whole_sync_and_writes_nothing(tmp_path):
    api = _PagingApi([_submission(n) for n in range(1, 251)], [])
    api.fail_on = ("submissions", 2)
    with pytest.raises(sync_netlify.NetlifySyncError):
        sync_netlify.sync("test-token", tmp_path, site_id=None, get_json=api)

    assert not (tmp_path / "submissions.json").exists()
    assert not (tmp_path / "ballots.json").exists()
    assert not (tmp_path / "id_map.json").exists()


def test_a_failed_ballot_page_leaves_submissions_untouched(tmp_path):
    # Fetch-everything-before-writing-anything: a ballot failure must not
    # leave a half-updated submissions.json behind.
    (tmp_path / "submissions.json").write_text('[{"id": "sub_001"}]', encoding="utf-8")
    api = _PagingApi([_submission(n) for n in range(1, 5)], [_ballot(n) for n in range(1, 251)])
    api.fail_on = ("ballots", 3)
    with pytest.raises(sync_netlify.NetlifySyncError):
        sync_netlify.sync("test-token", tmp_path, site_id=None, get_json=api)

    assert json.loads((tmp_path / "submissions.json").read_text(encoding="utf-8")) == [
        {"id": "sub_001"}
    ]


def test_a_non_list_page_is_an_error_not_a_silent_truncation(tmp_path):
    class _Weird(_PagingApi):
        def __call__(self, url, token, **kwargs):
            if urlsplit(url).path.endswith("/forms"):
                return FORMS
            return {"message": "rate limited"}

    with pytest.raises(sync_netlify.NetlifySyncError):
        sync_netlify.sync("test-token", tmp_path, site_id=None, get_json=_Weird([], []))


def test_runaway_pagination_is_bounded(tmp_path):
    class _NeverEnds:
        def __init__(self):
            self.calls = 0

        def __call__(self, url, token, **kwargs):
            if urlsplit(url).path.endswith("/forms"):
                return FORMS
            self.calls += 1
            return [_submission(self.calls * 1000 + i) for i in range(sync_netlify.PAGE_SIZE)]

    api = _NeverEnds()
    with pytest.raises(sync_netlify.NetlifySyncError):
        sync_netlify.sync("test-token", tmp_path, site_id=None, get_json=api)
    assert api.calls <= sync_netlify.MAX_PAGES + 1

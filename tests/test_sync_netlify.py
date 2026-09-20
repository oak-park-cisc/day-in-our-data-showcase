"""Unit tests for scripts/sync_netlify.py against fake Netlify API payloads.

No real HTTP call is ever made: `sync()` takes a `get_json` callable, and
every test supplies a fake one keyed by URL. This also exercises the
non-zero-exit-on-HTTP-error contract without touching a network.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "sync_netlify.py"
spec = importlib.util.spec_from_file_location("sync_netlify", SCRIPT_PATH)
sync_netlify = importlib.util.module_from_spec(spec)
sys.modules["sync_netlify"] = sync_netlify
spec.loader.exec_module(sync_netlify)  # type: ignore[union-attr]


FORMS_PAYLOAD = [
    {"id": "form-sub-123", "name": "submission", "site_id": "site-abc"},
    {"id": "form-ballot-456", "name": "ballot", "site_id": "site-abc"},
]

# A realistic-shaped Netlify Forms API submissions payload: top-level
# metadata plus a `data` dict of the raw field values, matching the
# `<form name="submission">` fields in site/index.html.
SUBMISSIONS_PAYLOAD = [
    {
        "id": "netlify-sub-2",
        "form_id": "form-sub-123",
        "created_at": "2026-10-03T14:45:00.000Z",
        "data": {
            "form-name": "submission",
            "team_name": "Parcel People",
            "project_title": "Assessment Fairness Dataset",
            "description": "A cleaned, documented dataset.",
            "solves_for": "Anyone checking their assessment.",
            "starter_project": "01-is-my-assessment-fair",
            "repo_url": "",
            "demo_url": "",
            "artifact": "https://netlify-uploads.example/assessments-clean.csv",
            "large_file_url": "https://drive.example/full-parcel-export",
        },
    },
    {
        "id": "netlify-sub-1",
        "form_id": "form-sub-123",
        "created_at": "2026-10-03T14:31:00.000Z",
        "data": {
            "form-name": "submission",
            "team_name": "Bike Lane Brigade",
            "project_title": "Safe Routes Gap Map",
            "description": "A map layering bike network and crash records.",
            "solves_for": "Parents deciding whether a kid can bike to school.",
            "starter_project": "04-can-a-kid-bike-to-school-safely",
            "repo_url": "https://github.com/example/safe-routes",
            "demo_url": "https://example.com/safe-routes",
            "artifact": {
                "url": "https://netlify-uploads.example/gap-map.png",
                "filename": "gap-map.png",
                "size": 482000,
            },
            "large_file_url": "",
        },
    },
]

BALLOTS_PAYLOAD = [
    {
        "id": "netlify-ballot-1",
        "form_id": "form-ballot-456",
        "created_at": "2026-10-03T16:05:00.000Z",
        "data": {
            "form-name": "ballot",
            "code": "abcdefghj2",
            "pick_1": "sub_001",
            "pick_2": "sub_002",
            "pick_3": "sub_003",
        },
    },
]


def fake_get_json(urls: dict[str, object]):
    def _get(url: str, token: str):
        assert token == "test-token"
        if url not in urls:
            raise AssertionError(f"unexpected URL requested: {url}")
        return urls[url]

    return _get


def default_urls():
    return {
        f"{sync_netlify.NETLIFY_API}/forms": FORMS_PAYLOAD,
        f"{sync_netlify.NETLIFY_API}/forms/form-sub-123/submissions": SUBMISSIONS_PAYLOAD,
        f"{sync_netlify.NETLIFY_API}/forms/form-ballot-456/submissions": BALLOTS_PAYLOAD,
    }


def test_resolve_form_id_matches_by_name_and_site():
    form_id = sync_netlify.resolve_form_id(FORMS_PAYLOAD, "ballot", "site-abc")
    assert form_id == "form-ballot-456"


def test_resolve_form_id_raises_when_missing():
    with pytest.raises(sync_netlify.NetlifySyncError):
        sync_netlify.resolve_form_id(FORMS_PAYLOAD, "not-a-form", None)


def test_resolve_form_id_raises_on_ambiguous_match():
    dupes = FORMS_PAYLOAD + [{"id": "form-sub-999", "name": "submission", "site_id": "site-xyz"}]
    with pytest.raises(sync_netlify.NetlifySyncError):
        sync_netlify.resolve_form_id(dupes, "submission", None)


def test_build_submissions_orders_by_submitted_at_and_assigns_ids_in_lockstep():
    submissions = sync_netlify.build_submissions(SUBMISSIONS_PAYLOAD)
    assert [s["id"] for s in submissions] == ["sub_001", "sub_002"]
    assert [s["anon_id"] for s in submissions] == ["P-01", "P-02"]
    # Payload was out of order (netlify-sub-2 listed first); confirm re-sort happened.
    assert submissions[0]["team_name"] == "Bike Lane Brigade"
    assert submissions[1]["team_name"] == "Parcel People"


def test_build_submissions_maps_every_contract_field():
    submissions = sync_netlify.build_submissions(SUBMISSIONS_PAYLOAD)
    bike = submissions[0]
    assert bike == {
        "id": "sub_001",
        "anon_id": "P-01",
        "team_name": "Bike Lane Brigade",
        "project_title": "Safe Routes Gap Map",
        "description": "A map layering bike network and crash records.",
        "solves_for": "Parents deciding whether a kid can bike to school.",
        "starter_project": "04-can-a-kid-bike-to-school-safely",
        "repo_url": "https://github.com/example/safe-routes",
        "demo_url": "https://example.com/safe-routes",
        "artifacts": [
            {
                "filename": "gap-map.png",
                "url": "https://netlify-uploads.example/gap-map.png",
                "bytes": 482000,
            }
        ],
        "large_file_url": None,
        "submitted_at": "2026-10-03T14:31:00.000Z",
    }


def test_build_submissions_handles_url_string_artifact_field():
    submissions = sync_netlify.build_submissions(SUBMISSIONS_PAYLOAD)
    parcel = submissions[1]
    assert parcel["artifacts"] == [
        {
            "filename": "assessments-clean.csv",
            "url": "https://netlify-uploads.example/assessments-clean.csv",
            "bytes": 0,
        }
    ]
    assert parcel["large_file_url"] == "https://drive.example/full-parcel-export"


def test_build_submissions_empty_optional_fields_become_none_not_empty_string():
    submissions = sync_netlify.build_submissions(SUBMISSIONS_PAYLOAD)
    parcel = submissions[1]
    assert parcel["repo_url"] is None
    assert parcel["demo_url"] is None


def test_missing_artifact_field_yields_empty_artifacts_list():
    raw = [{"created_at": "2026-10-03T15:00:00Z", "data": {}}]
    submissions = sync_netlify.build_submissions(raw)
    assert submissions[0]["artifacts"] == []


def test_build_ballots_hashes_code_and_never_stores_it_raw():
    ballots = sync_netlify.build_ballots(BALLOTS_PAYLOAD)
    assert len(ballots) == 1
    ballot = ballots[0]
    assert "code" not in ballot
    assert ballot["code_hash"] == hashlib.sha256(b"ABCDEFGHJ2").hexdigest()
    assert ballot["picks"] == ["sub_001", "sub_002", "sub_003"]
    assert ballot["cast_at"] == "2026-10-03T16:05:00.000Z"


def test_hash_code_normalizes_case_and_whitespace():
    assert sync_netlify._hash_code("abc123") == sync_netlify._hash_code(" ABC123 ")


def test_hash_code_is_deterministic_and_distinct_per_code():
    assert sync_netlify._hash_code("CODE001") == sync_netlify._hash_code("CODE001")
    assert sync_netlify._hash_code("CODE001") != sync_netlify._hash_code("CODE002")


def test_sync_writes_both_files(tmp_path):
    sync_netlify.sync(
        "test-token", tmp_path, site_id="site-abc", get_json=fake_get_json(default_urls())
    )
    submissions = json.loads((tmp_path / "submissions.json").read_text())
    ballots = json.loads((tmp_path / "ballots.json").read_text())
    assert len(submissions) == 2
    assert len(ballots) == 1
    raw_text = (tmp_path / "ballots.json").read_text()
    assert "abcdefghj2" not in raw_text.lower()  # the raw ballot code never reaches disk
    assert '"code":' not in raw_text  # only "code_hash" is ever a key, never plain "code"


def test_sync_raises_and_writes_nothing_on_form_lookup_failure(tmp_path):
    urls = default_urls()
    urls[f"{sync_netlify.NETLIFY_API}/forms"] = [{"id": "x", "name": "submission", "site_id": "site-abc"}]
    with pytest.raises(sync_netlify.NetlifySyncError):
        sync_netlify.sync("test-token", tmp_path, site_id="site-abc", get_json=fake_get_json(urls))
    assert not (tmp_path / "submissions.json").exists()
    assert not (tmp_path / "ballots.json").exists()


def test_sync_raises_and_writes_nothing_on_submissions_fetch_failure(tmp_path):
    def get_json(url: str, token: str):
        if url == f"{sync_netlify.NETLIFY_API}/forms":
            return FORMS_PAYLOAD
        raise sync_netlify.NetlifySyncError("Netlify API returned 500 for " + url)

    with pytest.raises(sync_netlify.NetlifySyncError):
        sync_netlify.sync("test-token", tmp_path, site_id="site-abc", get_json=get_json)
    assert not (tmp_path / "submissions.json").exists()
    assert not (tmp_path / "ballots.json").exists()


def test_main_exits_nonzero_when_token_missing(monkeypatch, capsys):
    monkeypatch.delenv("NETLIFY_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", ["sync_netlify.py"])
    assert sync_netlify.main() == 1
    assert "NETLIFY_TOKEN" in capsys.readouterr().err

"""Unit tests for scripts/sync_netlify.py against fake Netlify API payloads.

No real HTTP call is ever made: `sync()` takes a `get_json` callable, and
every test supplies a fake one keyed by URL. This also exercises the
non-zero-exit-on-HTTP-error contract without touching a network.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
import urllib.error
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
    def _get(url: str, token: str, **kwargs):
        # **kwargs absorbs include_body_in_errors -- the fake never makes a
        # real HTTP call so it has no body to withhold or include either way.
        assert token == "test-token"
        if url not in urls:
            raise AssertionError(f"unexpected URL requested: {url}")
        return urls[url]

    return _get


def submissions_url(form_id: str, page: int = 1) -> str:
    """The paginated URL sync() actually requests (see fetch_all_submissions)."""
    return (
        f"{sync_netlify.NETLIFY_API}/forms/{form_id}/submissions"
        f"?per_page={sync_netlify.PAGE_SIZE}&page={page}"
    )


def default_urls():
    return {
        f"{sync_netlify.NETLIFY_API}/forms": FORMS_PAYLOAD,
        submissions_url("form-sub-123"): SUBMISSIONS_PAYLOAD,
        submissions_url("form-ballot-456"): BALLOTS_PAYLOAD,
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
    # A Netlify `id` is now required on every raw submission: it is what
    # keeps the public sub_NNN stable when another submission is deleted
    # (see tests/test_sync_stable_ids.py).
    raw = [{"id": "nl-x", "created_at": "2026-10-03T15:00:00Z", "data": {}}]
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
    def get_json(url: str, token: str, **kwargs):
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


class _FakeHTTPResponse:
    """Minimal stand-in for the object urllib.request.urlopen() returns."""

    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def read(self) -> bytes:
        return self._body


def _http_error(url: str, code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "Error", {}, io.BytesIO(body))


def test_http_get_json_withholds_response_body_by_default(monkeypatch):
    """Finding 2, direct unit test: the safe default. Would fail against the
    pre-fix code, which always interpolated exc.read() into the message."""
    raw_code = "SUPERSECRETVOTERCODE9"
    body = json.dumps({"error": f"rejected: duplicate code {raw_code}"}).encode("utf-8")
    ballot_submissions_url = f"{sync_netlify.NETLIFY_API}/forms/form-ballot-456/submissions"

    def fake_urlopen(request, timeout=30):
        raise _http_error(request.full_url, 500, body)

    monkeypatch.setattr(sync_netlify.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(sync_netlify.NetlifySyncError) as excinfo:
        sync_netlify._http_get_json(ballot_submissions_url, "test-token")

    message = str(excinfo.value)
    assert raw_code not in message
    assert "500" in message
    assert ballot_submissions_url in message


def test_http_get_json_includes_response_body_when_explicitly_opted_in(monkeypatch):
    """The opt-in path still works, for the one call site (GET /forms) that
    has no voter data to protect and wants the detail for debugging."""
    body = b'{"error": "site not found or token lacks access"}'
    forms_url = f"{sync_netlify.NETLIFY_API}/forms"

    def fake_urlopen(request, timeout=30):
        raise _http_error(request.full_url, 404, body)

    monkeypatch.setattr(sync_netlify.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(sync_netlify.NetlifySyncError) as excinfo:
        sync_netlify._http_get_json(forms_url, "test-token", include_body_in_errors=True)

    assert "site not found or token lacks access" in str(excinfo.value)


def test_http_get_json_error_names_status_and_url_even_when_body_is_withheld(monkeypatch):
    body = b"raw upstream html error page, never shown"

    def fake_urlopen(request, timeout=30):
        raise _http_error(request.full_url, 503, body)

    monkeypatch.setattr(sync_netlify.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(sync_netlify.NetlifySyncError) as excinfo:
        sync_netlify._http_get_json("https://api.netlify.com/api/v1/forms/x/submissions", "test-token")

    message = str(excinfo.value)
    assert "503" in message
    assert "forms/x/submissions" in message
    assert "raw upstream html error page" not in message


def test_sync_never_leaks_a_raw_ballot_code_when_the_ballot_submissions_fetch_fails(monkeypatch, tmp_path):
    """The test that matters for Finding 2: exercises sync()'s REAL wiring
    (the actual _http_get_json, not a test fake), through the real HTTP code
    path with only urllib.request.urlopen mocked -- so this proves sync()
    itself never opts the ballot-submissions fetch into body-in-errors, not
    just that _http_get_json's default is safe in isolation. Built to fail
    against the pre-fix code: before the fix, _http_get_json always included
    exc.read() verbatim regardless of which endpoint it came from, so a raw
    code in this response body would have landed directly in the raised
    error's message.
    """
    raw_code = "ZQ7MFPLNK4XX"
    forms_body = json.dumps(FORMS_PAYLOAD).encode("utf-8")
    submissions_body = json.dumps(SUBMISSIONS_PAYLOAD).encode("utf-8")
    ballot_error_body = json.dumps({
        "message": f"could not process ballot with code={raw_code}",
    }).encode("utf-8")

    def fake_urlopen(request, timeout=30):
        url = request.full_url
        if url == f"{sync_netlify.NETLIFY_API}/forms":
            return _FakeHTTPResponse(forms_body)
        if url == submissions_url("form-sub-123"):
            return _FakeHTTPResponse(submissions_body)
        if url == submissions_url("form-ballot-456"):
            raise _http_error(url, 500, ballot_error_body)
        raise AssertionError(f"unexpected URL requested: {url}")

    monkeypatch.setattr(sync_netlify.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(sync_netlify.NetlifySyncError) as excinfo:
        sync_netlify.sync(
            "test-token", tmp_path, site_id="site-abc", get_json=sync_netlify._http_get_json
        )

    message = str(excinfo.value)
    assert raw_code not in message
    assert not (tmp_path / "submissions.json").exists()
    assert not (tmp_path / "ballots.json").exists()


def test_sync_forms_listing_error_may_include_its_body(monkeypatch, tmp_path):
    """Contrast case: the /forms listing call carries no voter data, so its
    error body is allowed through -- confirms the opt-in wiring in sync()
    actually reaches the real HTTP path, not just the default."""
    forms_error_body = b'{"error": "invalid or expired token"}'

    def fake_urlopen(request, timeout=30):
        raise _http_error(request.full_url, 401, forms_error_body)

    monkeypatch.setattr(sync_netlify.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(sync_netlify.NetlifySyncError) as excinfo:
        sync_netlify.sync(
            "test-token", tmp_path, site_id="site-abc", get_json=sync_netlify._http_get_json
        )

    assert "invalid or expired token" in str(excinfo.value)

"""Pull submitted projects and cast ballots from Netlify Forms into data/.

Run by .github/workflows/sync-submissions.yml (schedule + workflow_dispatch).
Requires NETLIFY_TOKEN (a Personal Access Token with access to the site) in
the environment. Writes data/submissions.json (the public §4.1 Submission
shape) and data/ballots.json (see the privacy note on _hash_code below).

Netlify assigns form ids only after the site is created and the form is
first detected (Task 16 Step 4, not done yet as of this script), so this
script never hardcodes a form id. Instead it lists every form the token can
see (GET /forms) and matches by the `name` attribute each form carries in
the HTML (`<form name="submission" ...>`, `<form name="ballot" ...>` -- see
site/index.html and site/vote.html). If NETLIFY_SITE_ID is set, matches are
also filtered to that site, which only matters if the token has access to
more than one site.

Exits non-zero on any HTTP error (a form not found counts as one) *before*
writing anything, so a failed sync never touches the previously committed,
known-good JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

NETLIFY_API = "https://api.netlify.com/api/v1"
SUBMISSION_FORM_NAME = "submission"
BALLOT_FORM_NAME = "ballot"

GetJSON = Callable[[str, str], Any]


class NetlifySyncError(RuntimeError):
    """Raised for any failure that should make the sync exit non-zero."""


def _http_get_json(url: str, token: str) -> Any:
    """Real HTTP GET against the Netlify API. Not used directly by tests."""
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise NetlifySyncError(f"Netlify API returned {exc.code} for {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise NetlifySyncError(f"Netlify API request failed for {url}: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise NetlifySyncError(f"Netlify API returned unparseable JSON for {url}: {exc}") from exc


def resolve_form_id(forms: list[dict], name: str, site_id: str | None) -> str:
    """Pick the form id whose `name` matches, optionally scoped to one site."""
    candidates = [f for f in forms if f.get("name") == name]
    if site_id:
        candidates = [f for f in candidates if f.get("site_id") == site_id]
    if not candidates:
        scope = f" on site {site_id}" if site_id else ""
        raise NetlifySyncError(f"No Netlify form named '{name}' found{scope}.")
    if len(candidates) > 1:
        raise NetlifySyncError(
            f"Multiple Netlify forms named '{name}' found; set NETLIFY_SITE_ID to disambiguate."
        )
    form_id = candidates[0].get("id")
    if not form_id:
        raise NetlifySyncError(f"Form '{name}' has no id in the Netlify API response.")
    return form_id


def _artifact_from(value: Any) -> dict | None:
    """Normalize a Netlify file-upload field into the §4.1 artifact shape.

    Netlify's Forms API most commonly represents an uploaded file's value as
    a plain URL string. Some accounts / API responses instead return a small
    object ({"url": ..., "filename": ..., "size": ...}). Both are handled;
    when only a URL is available, `filename` comes from the URL's last path
    segment and `bytes` defaults to 0 (unknown) rather than being guessed.
    This assumption could not be checked against the real API (see report).
    """
    if not value:
        return None
    if isinstance(value, dict):
        url = value.get("url")
        if not url:
            return None
        filename = value.get("filename") or url.rsplit("/", 1)[-1]
        size = value.get("size", 0) or 0
        return {"filename": filename, "url": url, "bytes": size}
    if isinstance(value, str):
        return {"filename": value.rsplit("/", 1)[-1], "url": value, "bytes": 0}
    return None


def _or_none(value: Any) -> str | None:
    return value if value else None


def map_submission(raw: dict, index: int) -> dict:
    """Map one raw Netlify submission to the §4.1 Submission shape.

    `index` is the submission's 1-based rank by submitted_at across the
    whole batch; it drives both `id` (sub_NNN, the public namespace) and
    `anon_id` (P-NN, the panel's blind namespace), assigned from the same
    ordering so the two stay in lockstep the way tests/fixtures/submissions.json
    already does (sub_001 <-> P-01, sub_002 <-> P-02, ...).
    """
    data = raw.get("data", {}) or {}
    artifact = _artifact_from(data.get("artifact"))
    return {
        "id": f"sub_{index:03d}",
        "anon_id": f"P-{index:02d}",
        "team_name": data.get("team_name", ""),
        "project_title": data.get("project_title", ""),
        "description": data.get("description", ""),
        "solves_for": data.get("solves_for", ""),
        "starter_project": data.get("starter_project", ""),
        "repo_url": _or_none(data.get("repo_url")),
        "demo_url": _or_none(data.get("demo_url")),
        "artifacts": [artifact] if artifact else [],
        "large_file_url": _or_none(data.get("large_file_url")),
        "submitted_at": raw.get("created_at"),
    }


def build_submissions(raw_submissions: list[dict]) -> list[dict]:
    ordered = sorted(raw_submissions, key=lambda r: r.get("created_at") or "")
    return [map_submission(r, i + 1) for i, r in enumerate(ordered)]


def _hash_code(code: str) -> str:
    """One-way hash a ballot code before it ever reaches a file that ships.

    data/ballots.json is committed to a public repo and copied verbatim into
    the published Netlify site (netlify.toml's build command). The design
    (§6.1 of the spec) is explicit that ballot codes never enter the repo --
    only the BALLOT_CODES Actions secret and the printed check-in slips
    carry them, precisely because a code sitting in public history could be
    used to cast a fraudulent ballot before its rightful holder votes.

    voting/tally.py already only ever compares `Ballot.code` for equality
    (is it in the valid set? has this code been used already?) and never
    copies it into a TallyResult (see tests/test_tally.py::
    test_codes_are_absent_from_the_result). Hashing the code here preserves
    that same property one step earlier, at rest: SHA-256 is a pure function
    of the code, so equality comparisons still work unchanged as long as the
    tally job hashes each BALLOT_CODES entry with this same function before
    comparing -- no change to voting/tally.py was needed or made.

    Not a secret-keyed HMAC: the code space is 32**10 (~1.13e15) possible
    values (see voting/generate_codes.py), so a plain hash is not brute-
    forceable from data/ballots.json alone, and using the BALLOT_CODES value
    itself as an HMAC key would require the sync job -- which never sees
    BALLOT_CODES -- to know a secret it isn't given.
    """
    normalized = code.strip().upper()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def map_ballot(raw: dict) -> dict:
    data = raw.get("data", {}) or {}
    picks = [data.get("pick_1", ""), data.get("pick_2", ""), data.get("pick_3", "")]
    return {
        "code_hash": _hash_code(data.get("code", "")),
        "picks": picks,
        "cast_at": raw.get("created_at"),
    }


def build_ballots(raw_ballots: list[dict]) -> list[dict]:
    return [map_ballot(r) for r in raw_ballots]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def sync(token: str, data_dir: Path, site_id: str | None = None, get_json: GetJSON = _http_get_json) -> None:
    """Fetch everything first; only write files once every fetch has succeeded."""
    forms = get_json(f"{NETLIFY_API}/forms", token)
    submission_form_id = resolve_form_id(forms, SUBMISSION_FORM_NAME, site_id)
    ballot_form_id = resolve_form_id(forms, BALLOT_FORM_NAME, site_id)

    raw_submissions = get_json(f"{NETLIFY_API}/forms/{submission_form_id}/submissions", token)
    raw_ballots = get_json(f"{NETLIFY_API}/forms/{ballot_form_id}/submissions", token)

    submissions = build_submissions(raw_submissions)
    ballots = build_ballots(raw_ballots)

    _write_json(data_dir / "submissions.json", submissions)
    _write_json(data_dir / "ballots.json", ballots)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Netlify Forms submissions into data/.")
    parser.add_argument("--data-dir", default="data", type=Path)
    args = parser.parse_args()

    token = os.environ.get("NETLIFY_TOKEN")
    if not token:
        print("NETLIFY_TOKEN is not set.", file=sys.stderr)
        return 1
    site_id = os.environ.get("NETLIFY_SITE_ID") or None

    try:
        sync(token, args.data_dir, site_id=site_id)
    except NetlifySyncError as exc:
        print(f"Netlify sync failed: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {args.data_dir / 'submissions.json'} and {args.data_dir / 'ballots.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

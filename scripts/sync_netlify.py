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

    This is NOT a strong defence on its own. The code alphabet is 32
    characters, 10 characters long (see voting/generate_codes.py), i.e. a
    2**50-ish space -- and unsalted SHA-256 over 2**50 candidates is a
    roughly 14-hour job on a single commodity GPU (~2.2e10 hashes/sec), or
    about 14 minutes expected time to the first hit against the ~60-odd
    hashes actually published in data/ballots.json at once. Sixty-plus bits
    is where a plain-hash argument starts holding; fifty is not enough on
    its own.

    What actually makes this acceptable is not the hash -- it's what's
    IN data/ballots.json: a code only appears there once someone has
    already POSTed a ballot with it, i.e. it already has a cast_at
    timestamp on record. tally.yml may run well after sync-submissions.yml
    publishes that code's hash, but tally() sorts all ballots by cast_at
    and keeps only the first VALID ballot per code (voting/tally.py; see
    tests/test_tally.py::test_reused_code_keeps_only_the_first_ballot). So
    even if an attacker cracks the hash minutes after it's published and
    immediately submits a competing ballot with the recovered code, that
    ballot's cast_at is later and loses at tally time regardless of when
    tally.yml happens to run -- the ordering, not the timing of tally.yml,
    is what protects it. (The one gap this doesn't close: if the genuine
    voter's own first submission was itself invalid -- e.g. duplicate
    picks -- and they haven't yet corrected it, a faster attacker's valid
    ballot on the same code could become the one that counts. Narrow, but
    real; not addressed by this hash.) The hash's job is only to keep an
    already-submitted code from sitting in the repo as recognizable
    plaintext, not to withstand an offline attack against a still-live,
    never-submitted code.

    This construction would NOT be safe for codes that are still unspent
    (e.g. if data/ballots.json ever held pending/unvalidated submissions,
    or if BALLOT_CODES itself were ever hashed and published this same way)
    -- an unspent code's hash is exactly as attackable as the 14-hour/
    14-minute figures above say. A keyed HMAC (using a secret the sync job
    doesn't currently receive) would be needed for that case; the repo
    owner is deciding separately whether to add a fourth secret for it.
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

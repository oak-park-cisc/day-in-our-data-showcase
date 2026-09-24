"""Pull submitted projects from Netlify Forms into data/, and read ballots for the tally.

Run by .github/workflows/sync-submissions.yml (schedule + workflow_dispatch).
Requires NETLIFY_TOKEN (a Personal Access Token with access to the site) in
the environment. Writes data/submissions.json (the public §4.1 Submission
shape) and data/id_map.json.

Ballots are NEVER written to disk. tally.yml calls fetch_ballots() and holds
them in memory only (spec 2026-09-24-free-tier-deployment-design.md §4.4):
the repo is public, and a committed ballot file lets anyone holding a slip
code read how that person voted.

Netlify assigns form ids only after the site is created and the form is
first detected (Task 16 Step 4, not done yet as of this script), so this
script never hardcodes a form id. Instead it lists every form the token can
see (GET /forms) and matches by the `name` attribute each form carries in
the HTML (`<form name="submission" ...>`, `<form name="ballot" ...>` -- see
site/index.html and site/vote.html). If NETLIFY_SITE_ID is set, matches are
also filtered to that site, which only matters if the token has access to
more than one site.

Both /submissions endpoints are PAGED (see fetch_all_submissions): the first
response is not the whole set, and treating it as such would make the tally
count a subset of ballots and publish it as the residents' verdict.

Exits non-zero on any HTTP error (a form not found counts as one, as does any
single page of a paginated fetch) *before* writing anything, so a failed sync
never touches the previously committed, known-good JSON.
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
#: Committed alongside submissions.json. Maps each Netlify submission id to
#: the public number it was issued, permanently. See assign_public_numbers.
ID_MAP_FILENAME = "id_map.json"
#: Netlify pages /submissions at 100 per request by default. Ask for that
#: explicitly and page until a short page comes back.
PAGE_SIZE = 100
#: 50,000 records at this event is impossible; a loop that gets there is a
#: paging bug or an API that ignores `page`, and must fail loudly rather
#: than spin forever inside a scheduled job.
MAX_PAGES = 500

GetJSON = Callable[..., Any]


class NetlifySyncError(RuntimeError):
    """Raised for any failure that should make the sync exit non-zero."""


def _http_get_json(url: str, token: str, *, include_body_in_errors: bool = False) -> Any:
    """Real HTTP GET against the Netlify API. Not used directly by tests.

    `include_body_in_errors` defaults to False -- an HTTPError's response
    body is withheld from the raised error's message *unless a caller opts
    in explicitly, per call*. This matters because GET .../submissions
    responses carry submitted form data, and for the ballot form that
    includes a voter's raw `code`. GitHub Actions only masks registered
    `secrets.*` values in a log; a voter's submitted code is never
    registered as one, so nothing redacts it if it ends up in a printed
    exception on a public repo's Actions log. Status code, method, and the
    endpoint path are always safe to include and always are.

    Defaulting to False (rather than True with call sites remembering to
    opt out) means a future call site added without thinking about this
    gets the safe behaviour automatically. Only sync()'s GET /forms listing
    call -- which returns form metadata, never submitted field data -- opts
    in, because its body is genuinely useful for debugging a 404/permission
    error and carries no voter data.
    """
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if include_body_in_errors:
            detail = exc.read().decode("utf-8", "replace")
        else:
            detail = "(response body withheld -- may contain submitted form data)"
        raise NetlifySyncError(f"Netlify API GET {url} returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise NetlifySyncError(f"Netlify API GET {url} failed: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise NetlifySyncError(f"Netlify API GET {url} returned unparseable JSON: {exc}") from exc


def fetch_all_submissions(get_json: GetJSON, form_id: str, token: str) -> list[dict]:
    """Every submission on a form, following pagination to the end.

    GET /forms/{id}/submissions is paged. Taking the first response as the
    whole set means that past 100 cast ballots the tally silently counts a
    subset and publishes it as the residents' verdict -- no error, no
    warning, wrong awards.

    A page shorter than PAGE_SIZE ends the loop; an exactly-full page is
    indistinguishable from "full, with more behind it" without asking, so it
    always asks. Any failure inside get_json propagates, which is what keeps
    sync()'s fetch-everything-before-writing-anything property: a failed page
    aborts the whole sync rather than committing a partial set.
    """
    collected: list[dict] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{NETLIFY_API}/forms/{form_id}/submissions?per_page={PAGE_SIZE}&page={page}"
        batch = get_json(url, token)
        if not isinstance(batch, list):
            raise NetlifySyncError(
                f"Netlify API GET {url} returned {type(batch).__name__}, not a list of "
                "submissions; refusing to treat that as an empty page."
            )
        collected.extend(batch)
        if len(batch) < PAGE_SIZE:
            return collected
    raise NetlifySyncError(
        f"Netlify API returned {MAX_PAGES} full pages for form {form_id} without ending; "
        "aborting rather than looping."
    )


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

    `index` is this submission's permanent public number (see
    assign_public_numbers); it drives both `id` (sub_NNN, the public
    namespace) and `anon_id` (P-NN, the panel's blind namespace), assigned
    from the same number so the two stay in lockstep the way
    tests/fixtures/submissions.json already does (sub_001 <-> P-01,
    sub_002 <-> P-02, ...).
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


def load_id_map(path: Path) -> dict[str, int]:
    """Read the committed Netlify-id -> public-number map, or {} on first run.

    A map that exists but cannot be read is a hard error: silently falling
    back to {} would renumber every submission, which is precisely the
    failure this file exists to prevent.
    """
    path = Path(path)
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise NetlifySyncError(f"{path} is not readable JSON: {exc}") from exc
    if not isinstance(loaded, dict) or not all(isinstance(v, int) for v in loaded.values()):
        raise NetlifySyncError(f"{path} is not a mapping of submission id -> integer.")
    return loaded


def assign_public_numbers(
    raw_submissions: list[dict], existing: dict[str, int] | None = None
) -> dict[str, int]:
    """Netlify submission id -> permanent public number.

    A submission's public number is assigned once and never changes, because
    ballots store the public id (sub_NNN) captured at vote time. Index-based
    numbering -- sort by created_at, number 1..N -- means that deleting ONE
    submission shifts every later one down, and every ballot naming sub_005
    silently starts counting for a different project. Spec §2.1 puts deleting
    a submission in scope as an admin action, and a public civic form will
    attract spam that someone will delete, so this is a matter of when.

    The returned map is a superset of `existing`: numbers issued to
    submissions that have since been deleted are RETAINED, so a deleted
    number is never reissued to a later team (which would be the same bug
    wearing a different hat). New submissions take the next free numbers in
    created_at order.

    A submission with no Netlify `id` raises rather than falling back to
    positional numbering.
    """
    numbers = dict(existing or {})
    ordered = sorted(raw_submissions, key=lambda r: r.get("created_at") or "")
    next_number = max(numbers.values(), default=0) + 1
    for raw in ordered:
        netlify_id = raw.get("id")
        if not netlify_id:
            raise NetlifySyncError(
                "A Netlify submission arrived with no `id`; refusing to assign public "
                "ids positionally, because that silently re-points cast ballots."
            )
        if netlify_id not in numbers:
            numbers[netlify_id] = next_number
            next_number += 1
    return numbers


def build_submissions(
    raw_submissions: list[dict], numbers: dict[str, int] | None = None
) -> list[dict]:
    """The §4.1 records, in created_at order, with stable public ids.

    `numbers` is the merged map from assign_public_numbers. Omitting it
    numbers this batch from scratch, which is only correct for a one-off or
    a first run -- sync() always passes the committed map.
    """
    if numbers is None:
        numbers = assign_public_numbers(raw_submissions)
    ordered = sorted(raw_submissions, key=lambda r: r.get("created_at") or "")
    return [map_submission(r, numbers[r["id"]]) for r in ordered]


def _hash_code(code: str) -> str:
    """One-way hash a ballot code so the tally compares hashes, not codes.

    tally.yml hashes every BALLOT_CODES entry with this same normalisation and
    compares for equality; voting/tally.py never copies a code into its
    result. Ballots are held in memory by tally.yml and never written to the
    repo or the site (spec 2026-09-24 §4.4), which is what protects ballot
    secrecy. The hash is not a secrecy mechanism and makes no claim to be one.
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


def fetch_ballots(token: str, site_id: str | None = None, get_json: GetJSON = _http_get_json) -> list[dict]:
    """Every cast ballot, hashed, for tally.yml to hold in memory. Never written.

    Only the /forms listing opts into include_body_in_errors (it carries no
    voter data). The ballot /submissions fetch takes _http_get_json's safe
    default, because its error body can echo a voter's raw code.
    """
    forms = get_json(f"{NETLIFY_API}/forms", token, include_body_in_errors=True)
    ballot_form_id = resolve_form_id(forms, BALLOT_FORM_NAME, site_id)
    return build_ballots(fetch_all_submissions(get_json, ballot_form_id, token))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def sync(token: str, data_dir: Path, site_id: str | None = None, get_json: GetJSON = _http_get_json) -> None:
    """Fetch everything first; only write files once every fetch has succeeded.

    Only the GET /forms listing opts into `include_body_in_errors` -- it
    returns form metadata, never submitted field data. The single
    /submissions fetch below, for the submission form, takes
    _http_get_json's safe default and does not opt in. Ballots are not
    fetched here at all: see fetch_ballots().
    """
    forms = get_json(f"{NETLIFY_API}/forms", token, include_body_in_errors=True)
    submission_form_id = resolve_form_id(forms, SUBMISSION_FORM_NAME, site_id)

    raw_submissions = fetch_all_submissions(get_json, submission_form_id, token)

    # The committed map is what makes sub_NNN survive a deleted submission.
    # It is read before anything is written and written back merged, never
    # pruned.
    numbers = assign_public_numbers(raw_submissions, load_id_map(data_dir / ID_MAP_FILENAME))
    submissions = build_submissions(raw_submissions, numbers)

    _write_json(data_dir / ID_MAP_FILENAME, numbers)
    _write_json(data_dir / "submissions.json", submissions)


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

    print(f"Wrote {args.data_dir / 'submissions.json'} and {args.data_dir / ID_MAP_FILENAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

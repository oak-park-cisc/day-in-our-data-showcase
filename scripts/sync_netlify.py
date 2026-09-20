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
#: Committed alongside submissions.json. Maps each Netlify submission id to
#: the public number it was issued, permanently. See assign_public_numbers.
ID_MAP_FILENAME = "id_map.json"

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
    """One-way hash a ballot code before it ever reaches a file that ships.

    SCOPE FIRST, because this docstring used to reason only about code
    recovery and that is not the whole risk. Two different properties are at
    stake:

    1. CODE RECOVERY -- can someone turn a published value back into a usable
       ballot code? That is what the hash addresses, and what the rest of this
       docstring argues about.
    2. BALLOT SECRECY -- can someone who ALREADY holds a plaintext code learn
       how that person voted? Hashing does nothing for this: the holder just
       hashes their copy of the code and looks the row up. The volunteer who
       handed out the slips, or anyone who photographs the slip sheet, is
       exactly that person. The only fix is not publishing the file, which is
       why netlify.toml's build command deletes ballots.json from the copy it
       pushes to the site (see that file's comment, and
       tests/test_netlify_config.py). data/ballots.json is still committed to
       the public repo, so anyone holding a plaintext code can still do this
       from the repo -- ballot secrecy here rests on the codes staying on the
       slips, not on the file being hard to reach. Removing it from the
       published site removes the one surface that required no repo access at
       all.

    data/ballots.json is committed to a public repo. The design
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

    (The netlify.toml deletion is about property 2 above; nothing in the
    paragraphs that follow changes because of it, since they are entirely
    about property 1.)

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
    """Fetch everything first; only write files once every fetch has succeeded.

    Only the GET /forms listing opts into `include_body_in_errors` -- it
    returns form metadata, never submitted field data. The two
    /submissions fetches below deliberately do NOT opt in (they take
    _http_get_json's safe default): one of them is the ballot form, whose
    submitted data includes a voter's raw code (see _http_get_json's
    docstring for why that specifically must never reach an error message).
    """
    forms = get_json(f"{NETLIFY_API}/forms", token, include_body_in_errors=True)
    submission_form_id = resolve_form_id(forms, SUBMISSION_FORM_NAME, site_id)
    ballot_form_id = resolve_form_id(forms, BALLOT_FORM_NAME, site_id)

    raw_submissions = get_json(f"{NETLIFY_API}/forms/{submission_form_id}/submissions", token)
    raw_ballots = get_json(f"{NETLIFY_API}/forms/{ballot_form_id}/submissions", token)

    # The committed map is what makes sub_NNN survive a deleted submission.
    # It is read before anything is written and written back merged, never
    # pruned.
    numbers = assign_public_numbers(raw_submissions, load_id_map(data_dir / ID_MAP_FILENAME))
    submissions = build_submissions(raw_submissions, numbers)
    ballots = build_ballots(raw_ballots)

    _write_json(data_dir / ID_MAP_FILENAME, numbers)
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

    print(
        f"Wrote {args.data_dir / 'submissions.json'}, "
        f"{args.data_dir / 'ballots.json'} and {args.data_dir / ID_MAP_FILENAME}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

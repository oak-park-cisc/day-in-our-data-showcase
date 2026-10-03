"""Enter projects in bulk through the live site's Netlify submission form.

For teams that built in Civic Spark but never pressed "Enter project". Each
CSV row is posted to the site exactly as the form on index.html would post
it, so the entry then flows through the normal pipeline (sync, gallery, AI
judging) with nothing special-cased. Step-by-step guide:
docs/bulk-load-guide.md.

    python scripts/bulk_submit.py entries.csv          # check only, sends nothing
    python scripts/bulk_submit.py entries.csv --send   # really submit

Columns: see docs/bulk-load-template.csv. `artifact_path` is a local file
(the team's Civic Spark zip), relative to the CSV's folder or absolute.

Rows whose team name + project title already appear on the live site are
skipped, so re-running after a partial failure does not create duplicates.
"""
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import re
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

SITE_URL = "https://oakparkciscdiod.netlify.app/"
LIVE_SUBMISSIONS = (
    "https://raw.githubusercontent.com/oak-park-cisc/day-in-our-data-showcase/main/data/submissions.json"
)
INDEX_HTML = Path(__file__).resolve().parent.parent / "site" / "index.html"
MAX_FILE_BYTES = 8 * 1024 * 1024

REQUIRED = ["team_name", "project_title", "description", "solves_for", "data_steps", "starter_project"]
URL_FIELDS = ["repo_url", "demo_url", "large_file_url"]
TEXT_FIELDS = REQUIRED + URL_FIELDS
COLUMNS = TEXT_FIELDS + ["artifact_path"]


def starter_projects(index_html: Path = INDEX_HTML) -> set[str]:
    """The starter_project values the real form offers, read from index.html."""
    html = index_html.read_text(encoding="utf-8")
    select = html[html.index('name="starter_project"'):]
    select = select[: select.index("</select>")]
    return {v for v in re.findall(r'<option value="([^"]+)"', select)}


@dataclass
class Entry:
    row: int
    fields: dict[str, str]
    artifact: Path | None
    problems: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return _key(self.fields["team_name"], self.fields["project_title"])


def _key(team: str, title: str) -> tuple[str, str]:
    return (" ".join(team.split()).casefold(), " ".join(title.split()).casefold())


def read_entries(csv_path: Path, allowed_starters: set[str]) -> list[Entry]:
    with csv_path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"{csv_path}: missing column(s): {', '.join(missing)}. "
                             "Start from docs/bulk-load-template.csv.")
        entries = []
        for n, raw in enumerate(reader, start=2):  # row 1 is the header
            if not any((v or "").strip() for v in raw.values()):
                continue
            fields = {c: (raw.get(c) or "").strip() for c in TEXT_FIELDS}
            problems = [f"{c} is empty" for c in REQUIRED if not fields[c]]
            if fields["starter_project"] and fields["starter_project"] not in allowed_starters:
                problems.append(f"starter_project {fields['starter_project']!r} is not one of the form's options")
            for c in URL_FIELDS:
                if fields[c] and not fields[c].startswith("https://"):
                    problems.append(f"{c} must start with https://")
            artifact = None
            path_text = (raw.get("artifact_path") or "").strip()
            if path_text:
                artifact = Path(path_text)
                if not artifact.is_absolute():
                    artifact = csv_path.parent / artifact
                if not artifact.is_file():
                    problems.append(f"artifact_path not found: {artifact}")
                elif artifact.stat().st_size > MAX_FILE_BYTES:
                    problems.append(f"artifact is over 8 MB ({artifact.stat().st_size // 1024 // 1024} MB); "
                                    "put a link in large_file_url instead")
            entries.append(Entry(n, fields, artifact, problems))
    return entries


def existing_keys(url: str = LIVE_SUBMISSIONS) -> set[tuple[str, str]]:
    with urllib.request.urlopen(url, timeout=30) as r:
        return {_key(s.get("team_name", ""), s.get("project_title", "")) for s in json.load(r)}


def encode_multipart(fields: dict[str, str], artifact: Path | None) -> tuple[bytes, str]:
    boundary = f"----diod{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in [("form-name", "submission"), *fields.items()]:
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    if artifact is not None:
        ctype = mimetypes.guess_type(artifact.name)[0] or "application/octet-stream"
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="artifact"; filename="{artifact.name}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n".encode("utf-8")
            + artifact.read_bytes()
            + b"\r\n"
        )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def post(entry: Entry, site_url: str = SITE_URL) -> int:
    body, ctype = encode_multipart(entry.fields, entry.artifact)
    req = urllib.request.Request(site_url, data=body, method="POST", headers={"Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enter projects in bulk through the Netlify form.")
    parser.add_argument("csv", type=Path)
    parser.add_argument("--send", action="store_true", help="Really submit. Without it, only checks.")
    args = parser.parse_args(argv)

    entries = read_entries(args.csv, starter_projects())
    if not entries:
        print("No rows found.")
        return 1
    try:
        already = existing_keys()
    except (urllib.error.URLError, ValueError) as exc:
        print(f"Could not read the live project list to check for duplicates: {exc}")
        return 1

    bad = [e for e in entries if e.problems]
    for e in entries:
        label = f"row {e.row}: {e.fields['team_name'] or '?'} - {e.fields['project_title'] or '?'}"
        if e.problems:
            print(f"FIX   {label}")
            for p in e.problems:
                print(f"        - {p}")
        elif e.key in already:
            print(f"SKIP  {label} (already on the site)")
        else:
            file_note = f", file {e.artifact.name}" if e.artifact else ", no file"
            print(f"READY {label}{file_note}")
    if bad:
        print(f"\n{len(bad)} row(s) need fixing. Nothing was sent.")
        return 1

    to_send = [e for e in entries if e.key not in already]
    if not args.send:
        print(f"\nCheck passed. {len(to_send)} row(s) would be sent. Re-run with --send to submit.")
        return 0

    failed = 0
    for e in to_send:
        try:
            status = post(e)
            print(f"SENT  row {e.row} (HTTP {status})")
        except urllib.error.URLError as exc:
            failed += 1
            print(f"ERROR row {e.row}: {exc}")
    print(f"\n{len(to_send) - failed} sent, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

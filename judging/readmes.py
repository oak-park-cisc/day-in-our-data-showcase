"""Fetch each team's README so the panel reads more than the entry form.

Owner decision (decision log #38): the panel reads the team's README, and
nothing else from their files -- no code, no data, no running app. Sources, in
order:

1. The uploaded artifact, when it is a zip (the Civic Spark export) or a
   README file on its own. Only the README entry closest to the zip's root is
   read; every other entry, including Civic Spark's shared PROJECT.md starter
   card, is ignored.
2. The linked GitHub repository's README, via the GitHub API (any README name,
   default branch).

Anything that fails -- a dead link, a private repo, a non-zip upload, an
oversized entry -- yields no README for that team, and the panel scores the
written entry alone, exactly as it did before this module existed. Failures are
never fatal: a README is extra evidence, not a requirement.

A README is participant-written text. It reaches the judges fenced and labelled
as data (see judging.prompts.evidence_block), and the panel decides nothing.
"""
from __future__ import annotations

import io
import os
import re
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import PurePosixPath

from judging.models import Submission

#: Characters of README the judges see. Enough for the five-heading template
#: the guides ask for; caps the cost and the room a README has to wander.
MAX_README_CHARS = 4000
#: Largest download attempted (the Netlify upload cap is 8 MB).
MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024
#: Largest single README entry decompressed from a zip.
MAX_ENTRY_BYTES = 512 * 1024
TIMEOUT_SECONDS = 20

README_NAMES = {"readme.md", "readme.txt", "readme", "readme.markdown"}
_FETCHABLE_SUFFIXES = {".zip", ".md", ".txt", ".markdown", ""}

#: Civic Spark seeds every project with this README. A team that never replaced
#: it has not written a README, so the template is not shown to the judges.
CIVIC_SPARK_TEMPLATE_MARKERS = (
    "# our community project",
    "start with a question your team cares about",
)

_GITHUB_REPO = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?(?:[/#?].*)?$")

Fetch = Callable[[str, dict[str, str]], bytes]


class FetchError(Exception):
    pass


def http_get(url: str, headers: dict[str, str]) -> bytes:
    if not url.startswith("https://"):
        raise FetchError("only https URLs are fetched")
    request = urllib.request.Request(url, headers={"User-Agent": "day-in-our-data-panel", **headers})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read(MAX_DOWNLOAD_BYTES + 1)
    except Exception as exc:  # network, HTTP status, TLS: all mean "no README"
        raise FetchError(str(exc)) from exc
    if len(body) > MAX_DOWNLOAD_BYTES:
        raise FetchError("download too large")
    return body


def is_template(text: str) -> bool:
    lowered = text.lower()
    return all(marker in lowered for marker in CIVIC_SPARK_TEMPLATE_MARKERS)


def _clean(raw: bytes) -> str | None:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text or is_template(text):
        return None
    if len(text) > MAX_README_CHARS:
        text = text[:MAX_README_CHARS].rstrip() + "\n[README truncated]"
    return text


def readme_from_zip(data: bytes) -> str | None:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return None
    with archive:
        candidates = [
            info for info in archive.infolist()
            if not info.is_dir()
            and PurePosixPath(info.filename).name.lower() in README_NAMES
            and "__MACOSX" not in info.filename
        ]
        if not candidates:
            return None
        best = min(candidates, key=lambda i: (len(PurePosixPath(i.filename).parts), i.filename))
        if best.file_size > MAX_ENTRY_BYTES:
            return None
        with archive.open(best) as entry:
            return _clean(entry.read(MAX_ENTRY_BYTES + 1)[:MAX_ENTRY_BYTES])


def _from_artifacts(sub: Submission, fetch: Fetch) -> str | None:
    for artifact in sub.artifacts:
        name = PurePosixPath(artifact.filename.lower())
        if name.suffix not in _FETCHABLE_SUFFIXES:
            continue
        try:
            data = fetch(artifact.url, {})
        except FetchError:
            continue
        if zipfile.is_zipfile(io.BytesIO(data)):
            text = readme_from_zip(data)
        elif name.name in README_NAMES:
            text = _clean(data[:MAX_ENTRY_BYTES])
        else:
            text = None
        if text:
            return text
    return None


def _from_github(sub: Submission, fetch: Fetch) -> str | None:
    match = _GITHUB_REPO.match(sub.repo_url or "")
    if not match:
        return None
    owner, repo = match.groups()
    headers = {"Accept": "application/vnd.github.raw+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        data = fetch(f"https://api.github.com/repos/{owner}/{repo}/readme", headers)
    except FetchError:
        return None
    return _clean(data[:MAX_ENTRY_BYTES])


def readme_for(sub: Submission, fetch: Fetch = http_get) -> str | None:
    return _from_artifacts(sub, fetch) or _from_github(sub, fetch)


def collect_readmes(submissions: list[Submission], fetch: Fetch = http_get) -> dict[str, str]:
    """README text keyed by submission id, for those that have one."""
    found: dict[str, str] = {}
    for sub in submissions:
        text = readme_for(sub, fetch)
        if text:
            found[sub.id] = text
    return found

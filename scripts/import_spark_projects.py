"""Enter every project from the event's project gallery that is not entered yet.

The gallery (https://oak-park-cisc.github.io/Oak_Park_Day_in_our_Data/) lists
the apps teams built in Civic Spark; their code is in the event repo under
projects/<slug>/. Many teams never pressed "Enter project". This script reads
the event repo's projects/README.md table, skips every project already on the
ranking site, builds the form fields from each project's own README, and
submits the rest through the live site's Netlify form via bulk_submit.py, so
they flow through the normal sync and judging pipeline.

    python scripts/import_spark_projects.py            # show what would be entered
    python scripts/import_spark_projects.py --send     # really enter them
    python scripts/import_spark_projects.py --check    # exit 1 if any project is missing

Duplicates are judged against data/submissions.json in this checkout, not the
raw.githubusercontent.com copy, which can lag a fresh sync by minutes. Run
`git pull` first when running it by hand.

Run by .github/workflows/import-spark-projects.yml. Safe to re-run: a project
already on the site, by team repository, title or team name, is skipped.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bulk_submit  # noqa: E402
import sync_netlify  # noqa: E402

EVENT_REPO = "oak-park-cisc/Oak_Park_Day_in_our_Data"
RAW = f"https://raw.githubusercontent.com/{EVENT_REPO}/main/projects"
GALLERY = "https://oak-park-cisc.github.io/Oak_Park_Day_in_our_Data/"
TREE = f"https://github.com/{EVENT_REPO}/tree/main/projects"
MAX_FIELD_CHARS = 1200
DISCLOSURE = "(Entered on the team's behalf from the Day in Our Data project gallery.)"
SPAM_SETTLE_SECONDS = 30
NOT_STATED = "Not stated in the team's README; see the project README and code."

SOLVES_HEADINGS = re.compile(r"civic question|bottom line|key findings|why|problem|potential users|purpose", re.I)
DATA_HEADINGS = re.compile(r"^(data|method|methods|how it works|how we built|sources?)\b", re.I)


@dataclass
class Project:
    slug: str
    title: str
    team: str
    team_repo: str | None


def fetch_text(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": "day-in-our-data-import"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def parse_manifest(md: str) -> list[Project]:
    """Rows of the `| Project | Team | Code |` table in projects/README.md."""
    projects = []
    for line in md.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] in ("Project", "") or set(cells[0]) <= set("-: "):
            continue
        slug = re.search(r"\]\(([a-z0-9-]+)\)", cells[2])
        if not slug:
            continue
        team_repo = re.search(r"\[team repo\]\((https://github\.com/[^)]+)\)", cells[2])
        projects.append(Project(slug.group(1), cells[0], cells[1], team_repo.group(1) if team_repo else None))
    return projects


def parse_gallery_topics(page: str) -> dict[str, str]:
    """slug -> the gallery card's one-line topic (the text after "Team ·")."""
    topics = {}
    for slug, line in re.findall(r'<a class="open" href="([a-z0-9-]+)/">.*?</a><p>(.*?)</p>', page):
        line = html.unescape(re.sub(r"<[^>]+>", "", line))
        if " · " in line:
            topics[slug] = line.split(" · ", 1)[1].strip()
    return topics


def _plain(markdown: str) -> str:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s*(#+|[-*]|\d+\.)\s*", "", text, flags=re.M)
    text = re.sub(r"[`*_>|]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > MAX_FIELD_CHARS:
        text = text[:MAX_FIELD_CHARS].rsplit(" ", 1)[0] + " …"
    return text


def sections(readme: str) -> tuple[str, list[tuple[str, str]]]:
    """(intro before the first ## heading, [(heading, body), ...])."""
    parts = re.split(r"^##\s+(.+)$", readme, flags=re.M)
    intro = re.sub(r"^#\s+.*$", "", parts[0], count=1, flags=re.M)
    return intro, [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


def is_spark_template(text: str) -> bool:
    lowered = text.lower()
    return "# our community project" in lowered and "start with a question your team cares about" in lowered


def starter_for(project_md: str | None, options: dict[str, str]) -> str:
    """Match PROJECT.md's title, or its "Original brief:" line, to a starter label."""
    if project_md:
        candidates = re.findall(r"^#+\s+(?:Original brief:\s*)?(.+)$", project_md, flags=re.M)
        for candidate in candidates:
            wanted = candidate.strip().casefold().rstrip("?")
            for value, label in options.items():
                if label.casefold().rstrip("?") == wanted:
                    return value
    return "pitch-your-own"


def starter_options(index_html: Path = bulk_submit.INDEX_HTML) -> dict[str, str]:
    page = index_html.read_text(encoding="utf-8")
    select = page[page.index('name="starter_project"'):]
    select = select[: select.index("</select>")]
    return {
        v: re.sub(r"^\d+\s*·\s*", "", html.unescape(label)).strip()
        for v, label in re.findall(r'<option value="([^"]+)">([^<]+)</option>', select)
    }


def build_fields(project: Project, topic: str | None, readme: str | None, project_md: str | None,
                 options: dict[str, str]) -> dict[str, str]:
    intro, secs = sections(readme or "")
    template = is_spark_template(readme or "")
    if template:
        # Civic Spark's seeded text is not the team's; keep only sections they added.
        intro = ""
        secs = [(h, b) for h, b in secs if not h.lower().startswith("first steps")]

    description_parts = [topic[:1].upper() + topic[1:] + "." if topic else "", _plain(intro)]
    if not _plain(intro) and secs:
        description_parts.append(_plain(secs[0][1]))
    description = " ".join(p for p in description_parts if p).strip()
    description = f"{description} {DISCLOSURE}".strip() if description else DISCLOSURE

    starter = starter_for(project_md, options)
    solves = next((_plain(b) for h, b in secs if SOLVES_HEADINGS.search(h) and _plain(b)), "")
    if not solves and project_md and starter != "pitch-your-own":
        q = re.search(r"\*\*Civic question:\*\*\s*(.+)", project_md)
        solves = f"The starter question: {q.group(1).strip()}" if q else ""
    data = next((_plain(b) for h, b in secs if DATA_HEADINGS.search(h) and _plain(b)), "")

    return {
        "team_name": project.team,
        "project_title": project.title,
        "description": description,
        "solves_for": solves or NOT_STATED,
        "data_steps": data or NOT_STATED,
        "starter_project": starter,
        "repo_url": project.team_repo or f"{TREE}/{project.slug}",
        "demo_url": f"{GALLERY}{project.slug}/",
        "large_file_url": "",
    }


def _norm(text: str | None) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", (text or "").casefold())
    words = [w for w in text.split() if w != "team"]
    return " ".join(words)


def already_entered(project: Project, submissions: list[dict]) -> dict | None:
    """The existing entry for this project, matched by team repo, title or team name."""
    for s in submissions:
        repo = (s.get("repo_url") or "").rstrip("/").removesuffix(".git").casefold()
        if project.team_repo and repo == project.team_repo.rstrip("/").casefold():
            return s
        if repo and repo == f"{TREE}/{project.slug}".casefold():
            return s
        if _norm(s.get("project_title")) == _norm(project.title):
            return s
        if _norm(project.team) and _norm(s.get("team_name")) == _norm(project.team):
            return s
    return None


REPO_SUBMISSIONS = Path(__file__).resolve().parent.parent / "data" / "submissions.json"


def load_submissions(path: Path = REPO_SUBMISSIONS) -> list[dict]:
    import json
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def plan(submissions: list[dict]) -> tuple[list[bulk_submit.Entry], list[tuple[Project, dict]]]:
    projects = parse_manifest(fetch_text(f"{RAW}/README.md") or "")
    if not projects:
        raise SystemExit("Could not read the project table from the event repo's projects/README.md.")
    topics = parse_gallery_topics(fetch_text(GALLERY) or "")
    options = starter_options()
    to_enter, skipped = [], []
    for n, p in enumerate(projects, start=1):
        existing = already_entered(p, submissions)
        if existing:
            skipped.append((p, existing))
            continue
        fields = build_fields(p, topics.get(p.slug), fetch_text(f"{RAW}/{p.slug}/README.md"),
                              fetch_text(f"{RAW}/{p.slug}/PROJECT.md"), options)
        to_enter.append(bulk_submit.Entry(row=n, fields=fields, artifact=None))
    return to_enter, skipped


class SpamCheckError(RuntimeError):
    pass


def _netlify_put(url: str, token: str) -> None:
    req = urllib.request.Request(url, data=b"", method="PUT", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30):
            pass
    except urllib.error.HTTPError as exc:
        raise SpamCheckError(f"PUT {url} returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise SpamCheckError(f"PUT {url} failed: {exc.reason}") from exc


def release_from_spam(keys: set[tuple[str, str]], token: str, site_id: str | None,
                      get_json=sync_netlify._http_get_json, put=_netlify_put) -> set[tuple[str, str]]:
    """Mark as Not spam every `submission` entry in Netlify's spam folder whose
    team + title is one of `keys` (the gallery projects this script enters).
    Anything else in the spam folder is left alone. Returns the keys released.

    Netlify's spam filter can hold form posts that did not come from a browser;
    the sync only reads accepted entries, so a held import never reaches the site.
    """
    try:
        forms = sync_netlify._site_forms(get_json, token, site_id)
        form_id = sync_netlify.resolve_form_id(forms, sync_netlify.SUBMISSION_FORM_NAME, None)
        released: set[tuple[str, str]] = set()
        for page in range(1, sync_netlify.MAX_PAGES + 1):
            url = (f"{sync_netlify.NETLIFY_API}/forms/{form_id}/submissions"
                   f"?state=spam&per_page={sync_netlify.PAGE_SIZE}&page={page}")
            batch = get_json(url, token)
            if not isinstance(batch, list):
                raise SpamCheckError("the spam listing was not a list")
            for raw in batch:
                data = raw.get("data") or {}
                key = bulk_submit._key(data.get("team_name", ""), data.get("project_title", ""))
                if key in keys:
                    put(f"{sync_netlify.NETLIFY_API}/submissions/{raw['id']}/ham", token)
                    released.add(key)
            if len(batch) < sync_netlify.PAGE_SIZE:
                break
        return released
    except sync_netlify.NetlifySyncError as exc:
        raise SpamCheckError(str(exc)) from exc


def _release(keys, token, site_id, label: str) -> set[tuple[str, str]]:
    if not keys or not token:
        return set()
    try:
        released = release_from_spam(keys, token, site_id)
    except SpamCheckError as exc:
        print(f"WARN  could not check Netlify's spam folder {label}: {exc}. "
              "If projects are missing after the sync, mark them Not spam in "
              "Netlify -> Forms -> submission -> Spam.")
        return set()
    for key in sorted(released):
        print(f"FREED {key[1]} ({key[0]}): released from Netlify's spam folder {label}")
    return released


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enter gallery projects that are not on the ranking site yet.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--send", action="store_true", help="Really submit. Without it, only shows the plan.")
    mode.add_argument("--check", action="store_true",
                      help="Exit 1 if any gallery project is not on the site yet (after a sync).")
    parser.add_argument("--submissions", type=Path, default=REPO_SUBMISSIONS)
    args = parser.parse_args(argv)

    to_enter, skipped = plan(load_submissions(args.submissions))
    for p, s in skipped:
        print(f"SKIP  {p.title} ({p.team}): already entered as {s['id']} \"{s.get('project_title')}\"")
    for e in to_enter:
        f = e.fields
        print(f"\nNEW   {f['project_title']} ({f['team_name']})")
        for key in ("starter_project", "repo_url", "demo_url", "description", "solves_for", "data_steps"):
            print(f"      {key}: {f[key]}")
    if not to_enter:
        print("\nEvery gallery project is already entered. Nothing to do.")
        return 0
    if args.check:
        print(f"\n{len(to_enter)} project(s) were sent but are not on the site after the sync. "
              "Check Netlify -> Forms -> submission -> Spam, mark them Not spam, then run the sync again.")
        return 1
    if not args.send:
        print(f"\n{len(to_enter)} project(s) would be entered. Re-run with --send to submit.")
        return 0

    import os
    import time

    token = os.environ.get("NETLIFY_TOKEN")
    site_id = os.environ.get("NETLIFY_SITE_ID") or None
    if not token:
        print("NOTE  NETLIFY_TOKEN is not set, so Netlify's spam folder is not checked.")

    # An earlier run may have sent these already and Netlify held them as spam:
    # release those instead of sending them a second time. If the spam folder
    # cannot be read, stop: sending blind could duplicate a held entry.
    held: set[tuple[str, str]] = set()
    if token:
        try:
            held = release_from_spam({e.key for e in to_enter}, token, site_id)
        except SpamCheckError as exc:
            print(f"STOP  could not read Netlify's spam folder ({exc}), so nothing was sent: an "
                  "earlier run's entries may be held there. Mark them Not spam in Netlify -> Forms "
                  "-> submission -> Spam and run the sync, or run this without NETLIFY_TOKEN to send anyway.")
            return 1
        for key in sorted(held):
            print(f"FREED {key[1]} ({key[0]}): released from Netlify's spam folder (sent by an earlier run)")
    to_send = [e for e in to_enter if e.key not in held]

    failed = 0
    sent = []
    for e in to_send:
        try:
            status = bulk_submit.post(e)
            sent.append(e)
            print(f"SENT  {e.fields['project_title']} (HTTP {status})")
        except urllib.error.URLError as exc:
            failed += 1
            print(f"ERROR {e.fields['project_title']}: {exc}")

    if sent and token:
        time.sleep(SPAM_SETTLE_SECONDS)  # Netlify files a post as spam or not within seconds
        _release({e.key for e in sent}, token, site_id, "(just sent)")
    print(f"\n{len(sent)} entered, {len(held)} released from spam, {failed} failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

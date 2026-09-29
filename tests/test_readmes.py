"""judging.readmes: which README the panel reads, and when it reads none."""
from __future__ import annotations

import io
import zipfile
from datetime import datetime

from judging.models import Artifact, Submission
from judging.readmes import (
    MAX_README_CHARS,
    FetchError,
    collect_readmes,
    http_get,
    readme_for,
    readme_from_zip,
)

# The README Civic Spark seeds every project with (from a real team export).
CIVIC_SPARK_TEMPLATE = """# Our community project

Start with a question your team cares about. Explore the files, edit them yourself, or ask an agent for help.

## First steps

1. Choose a question and record it here.
"""

TEAM_README = "# Bus stop audit\n\n## How we got the numbers\nFiltered stops.csv to Pace routes."


def make_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def sub(artifacts=(), repo_url=None) -> Submission:
    return Submission(
        id="sub_001", anon_id="P-01", team_name="T", project_title="P",
        description="d", solves_for="s", starter_project="06-which-bus-stops-need-help",
        repo_url=repo_url, artifacts=list(artifacts), submitted_at=datetime(2026, 10, 3, 14, 0),
    )


def fake_fetch(responses: dict[str, bytes]):
    calls: list[tuple[str, dict]] = []

    def fetch(url: str, headers: dict[str, str]) -> bytes:
        calls.append((url, headers))
        if url not in responses:
            raise FetchError("404")
        return responses[url]

    fetch.calls = calls
    return fetch


ZIP_URL = "https://uploads.example/team-project.zip"


def test_civic_spark_export_reads_the_team_readme_not_project_md():
    data = make_zip({
        "project/README.md": TEAM_README,
        "project/PROJECT.md": "# Starter card shared by every team",
        "project/data/sample.csv": "a,b\n1,2\n",
    })
    assert readme_from_zip(data) == TEAM_README


def test_an_unedited_civic_spark_template_counts_as_no_readme():
    data = make_zip({"project/README.md": CIVIC_SPARK_TEMPLATE, "project/PROJECT.md": "card"})
    assert readme_from_zip(data) is None


def test_the_readme_nearest_the_root_wins():
    data = make_zip({
        "project/README.md": TEAM_README,
        "project/node_modules/lib/README.md": "a dependency's readme",
    })
    assert readme_from_zip(data) == TEAM_README


def test_a_long_readme_is_truncated_and_marked():
    data = make_zip({"README.md": "x" * (MAX_README_CHARS + 500)})
    text = readme_from_zip(data)
    assert text.endswith("[README truncated]")
    assert len(text) < MAX_README_CHARS + 50


def test_uploaded_zip_is_used_before_the_repository():
    fetch = fake_fetch({
        ZIP_URL: make_zip({"project/README.md": TEAM_README}),
        "https://api.github.com/repos/team/repo/readme": b"# From GitHub",
    })
    s = sub([Artifact(filename="team-project.zip", url=ZIP_URL, bytes=5025)],
            "https://github.com/team/repo")
    assert readme_for(s, fetch) == TEAM_README


def test_github_readme_is_read_when_there_is_no_zip():
    fetch = fake_fetch({"https://api.github.com/repos/team/repo/readme": b"# From GitHub"})
    s = sub(repo_url="https://github.com/team/repo.git")
    assert readme_for(s, fetch) == "# From GitHub"
    assert fetch.calls[0][1]["Accept"] == "application/vnd.github.raw+json"


def test_github_url_with_a_path_still_resolves_to_the_repo():
    fetch = fake_fetch({"https://api.github.com/repos/team/repo/readme": b"# From GitHub"})
    s = sub(repo_url="https://github.com/team/repo/tree/main/src")
    assert readme_for(s, fetch) == "# From GitHub"


def test_images_and_pdfs_are_never_downloaded():
    fetch = fake_fetch({})
    s = sub([Artifact(filename="map.png", url="https://uploads.example/map.png", bytes=9),
             Artifact(filename="slides.pdf", url="https://uploads.example/slides.pdf", bytes=9)])
    assert readme_for(s, fetch) is None
    assert fetch.calls == []


def test_every_failure_means_no_readme_not_a_crash():
    fetch = fake_fetch({})  # every URL 404s
    s = sub([Artifact(filename="team-project.zip", url=ZIP_URL, bytes=1)],
            "https://github.com/team/private-repo")
    assert readme_for(s, fetch) is None


def test_a_non_github_repo_link_is_not_fetched():
    fetch = fake_fetch({})
    assert readme_for(sub(repo_url="https://gitlab.com/team/repo"), fetch) is None
    assert fetch.calls == []


def test_collect_readmes_keys_by_submission_id_and_skips_misses():
    fetch = fake_fetch({ZIP_URL: make_zip({"README.md": TEAM_README})})
    with_zip = sub([Artifact(filename="team-project.zip", url=ZIP_URL, bytes=1)])
    without = sub().model_copy(update={"id": "sub_002", "anon_id": "P-02"})
    assert collect_readmes([with_zip, without], fetch) == {"sub_001": TEAM_README}


def test_http_get_refuses_plain_http():
    try:
        http_get("http://example.com/README.md", {})
    except FetchError:
        return
    raise AssertionError("plain http must not be fetched")

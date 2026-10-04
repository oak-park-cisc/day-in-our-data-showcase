"""scripts/import_spark_projects.py: gallery projects -> Netlify entries, never twice."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("import_spark_projects", ROOT / "scripts" / "import_spark_projects.py")
isp = importlib.util.module_from_spec(spec)
sys.modules["import_spark_projects"] = isp
spec.loader.exec_module(isp)

MANIFEST = """# Day in Our Data 2026 projects

| Project | Team | Code |
|---|---|---|
| Lorax | Lorax team | [projects/lorax](lorax) |
| Oak Park Safe Routes | Team Shadowbat | [projects/oak-park-safe-routes](oak-park-safe-routes) · [team repo](https://github.com/Shawdowbat/OakParkCrimeWebApp) |
| Urban Forest Diversity | Urban Forest Diversity team | [projects/urban-forest-diversity](urban-forest-diversity) |
"""

GALLERY = (
    '<div class="card"><a class="open" href="lorax/"><h2>Lorax</h2></a>'
    "<p>Lorax team · urban forest canopy, MODIS satellite cover</p></div>"
    '<div class="card"><a class="open" href="team-wesley/"><h2>Survivor</h2></a><p>Team Wesley</p></div>'
)

EXISTING = [
    {"id": "sub_005", "team_name": "Team Shadowbat", "project_title": "Oak Park Crime Web App",
     "repo_url": "https://github.com/Shawdowbat/OakParkCrimeWebApp"},
    {"id": "sub_006", "team_name": "Urban Forest Diversity", "project_title": "How resilient is our urban forest?",
     "repo_url": None},
]


def test_manifest_rows_parse_with_team_repos():
    projects = isp.parse_manifest(MANIFEST)
    assert [p.slug for p in projects] == ["lorax", "oak-park-safe-routes", "urban-forest-diversity"]
    assert projects[1].team_repo == "https://github.com/Shawdowbat/OakParkCrimeWebApp"
    assert projects[0].team_repo is None


def test_gallery_topics_take_the_text_after_the_team():
    assert isp.parse_gallery_topics(GALLERY) == {"lorax": "urban forest canopy, MODIS satellite cover"}


def test_projects_entered_under_another_name_are_recognised():
    projects = {p.slug: p for p in isp.parse_manifest(MANIFEST)}
    # Same team repo, different title.
    assert isp.already_entered(projects["oak-park-safe-routes"], EXISTING)["id"] == "sub_005"
    # Same team once "team" is ignored, different title.
    assert isp.already_entered(projects["urban-forest-diversity"], EXISTING)["id"] == "sub_006"
    assert isp.already_entered(projects["lorax"], EXISTING) is None


def test_an_imported_project_is_recognised_by_its_folder_link():
    lorax = isp.parse_manifest(MANIFEST)[0]
    imported = [{"id": "sub_007", "team_name": "x", "project_title": "y",
                 "repo_url": f"{isp.TREE}/lorax"}]
    assert isp.already_entered(lorax, imported)["id"] == "sub_007"


def test_starter_is_matched_from_title_or_original_brief():
    options = isp.starter_options()
    assert isp.starter_for("# How resilient is our urban forest?\n", options) == "11-how-resilient-is-our-urban-forest"
    assert isp.starter_for("# Survivor\n\n## Original brief: Is my assessment fair?\n", options) == "01-is-my-assessment-fair"
    assert isp.starter_for("# Something new\n", options) == "pitch-your-own"
    assert isp.starter_for(None, options) == "pitch-your-own"


def test_fields_come_from_the_readme_and_pass_form_validation(tmp_path):
    readme = (
        "# Lorax\n\nA map of tree diversity on every block.\n\n"
        "## Civic question\n\nWhich blocks depend on one genus?\n\n"
        "## Data\n\nThe Village tree inventory, snapped to blocks.\n"
    )
    lorax = isp.parse_manifest(MANIFEST)[0]
    f = isp.build_fields(lorax, "urban forest canopy, MODIS", readme, None, isp.starter_options())
    assert f["description"].startswith("Urban forest canopy, MODIS. A map of tree diversity")
    assert f["description"].endswith(isp.DISCLOSURE)
    assert f["solves_for"] == "Which blocks depend on one genus?"
    assert f["data_steps"] == "The Village tree inventory, snapped to blocks."
    assert f["repo_url"] == f"{isp.TREE}/lorax"
    assert f["demo_url"] == f"{isp.GALLERY}lorax/"
    # The same checks bulk_submit applies to a hand-filled CSV.
    import csv
    path = tmp_path / "e.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=isp.bulk_submit.COLUMNS)
        w.writeheader()
        w.writerow({**f, "artifact_path": ""})
    entries = isp.bulk_submit.read_entries(path, isp.bulk_submit.starter_projects())
    assert entries[0].problems == []


def test_civic_spark_template_text_is_not_used_as_the_teams_words():
    readme = (
        "# Our community project\n\nStart with a question your team cares about. Explore the files.\n\n"
        "## First steps\n\n1. Choose a question.\n\n## Oak Park urban forest map\n\nFilters by species.\n"
    )
    lorax = isp.parse_manifest(MANIFEST)[0]
    f = isp.build_fields(lorax, None, readme, None, isp.starter_options())
    assert "Start with a question" not in f["description"]
    assert "Choose a question" not in f["description"]
    assert "Filters by species." in f["description"]


def test_missing_answers_say_so_instead_of_inventing_them():
    lorax = isp.parse_manifest(MANIFEST)[0]
    f = isp.build_fields(lorax, None, None, None, isp.starter_options())
    assert f["solves_for"] == isp.NOT_STATED
    assert f["data_steps"] == isp.NOT_STATED
    assert f["description"] == isp.DISCLOSURE


def test_check_mode_fails_when_a_project_is_still_missing(monkeypatch, tmp_path):
    lorax = isp.parse_manifest(MANIFEST)[0]
    entry = isp.bulk_submit.Entry(row=1, fields=isp.build_fields(lorax, None, None, None, isp.starter_options()),
                                  artifact=None)
    monkeypatch.setattr(isp, "plan", lambda subs: ([entry], []))
    sent = []
    monkeypatch.setattr(isp.bulk_submit, "post", lambda e: sent.append(e) or 200)
    assert isp.main(["--check", "--submissions", str(tmp_path / "none.json")]) == 1
    assert isp.main(["--submissions", str(tmp_path / "none.json")]) == 0
    assert sent == []
    monkeypatch.setattr(isp, "plan", lambda subs: ([], []))
    assert isp.main(["--check", "--submissions", str(tmp_path / "none.json")]) == 0


def _spam_fakes(spam_entries):
    forms = [{"id": "form-sub", "name": "submission"}]
    puts = []

    def get_json(url, token, **_):
        if url.endswith("/forms"):
            return forms
        assert "state=spam" in url
        return spam_entries if "page=1" in url else []

    return get_json, puts


def test_only_gallery_projects_are_released_from_spam():
    spam = [
        {"id": "s1", "data": {"team_name": "Lorax team", "project_title": "Lorax"}},
        {"id": "s2", "data": {"team_name": "Casino Bonus", "project_title": "WIN NOW"}},
    ]
    get_json, puts = _spam_fakes(spam)
    released = isp.release_from_spam({isp.bulk_submit._key("Lorax team", "Lorax")}, "tok", "site",
                                     get_json=get_json, put=lambda url, token: puts.append(url))
    assert released == {isp.bulk_submit._key("Lorax team", "Lorax")}
    assert puts == [f"{isp.sync_netlify.NETLIFY_API}/submissions/s1/ham"]


def test_a_project_held_in_spam_is_released_not_sent_again(monkeypatch, tmp_path):
    lorax = isp.parse_manifest(MANIFEST)[0]
    entry = isp.bulk_submit.Entry(row=1, fields=isp.build_fields(lorax, None, None, None, isp.starter_options()),
                                  artifact=None)
    monkeypatch.setattr(isp, "plan", lambda subs: ([entry], []))
    monkeypatch.setenv("NETLIFY_TOKEN", "tok")
    monkeypatch.setattr(isp, "release_from_spam", lambda keys, token, site_id: set(keys))
    sent = []
    monkeypatch.setattr(isp.bulk_submit, "post", lambda e: sent.append(e) or 200)
    assert isp.main(["--send", "--submissions", str(tmp_path / "none.json")]) == 0
    assert sent == []


def test_an_unreadable_spam_folder_stops_before_sending(monkeypatch, tmp_path, capsys):
    """Sending blind could duplicate an entry an earlier run left held in spam."""
    lorax = isp.parse_manifest(MANIFEST)[0]
    entry = isp.bulk_submit.Entry(row=1, fields=isp.build_fields(lorax, None, None, None, isp.starter_options()),
                                  artifact=None)
    monkeypatch.setattr(isp, "plan", lambda subs: ([entry], []))
    monkeypatch.setenv("NETLIFY_TOKEN", "tok")

    def broken(keys, token, site_id):
        raise isp.SpamCheckError("HTTP 404")

    monkeypatch.setattr(isp, "release_from_spam", broken)
    sent = []
    monkeypatch.setattr(isp.bulk_submit, "post", lambda e: sent.append(e) or 200)
    assert isp.main(["--send", "--submissions", str(tmp_path / "none.json")]) == 1
    assert sent == []
    assert "STOP" in capsys.readouterr().out


def test_without_a_token_it_sends_without_checking_spam(monkeypatch, tmp_path):
    lorax = isp.parse_manifest(MANIFEST)[0]
    entry = isp.bulk_submit.Entry(row=1, fields=isp.build_fields(lorax, None, None, None, isp.starter_options()),
                                  artifact=None)
    monkeypatch.setattr(isp, "plan", lambda subs: ([entry], []))
    monkeypatch.delenv("NETLIFY_TOKEN", raising=False)
    sent = []
    monkeypatch.setattr(isp.bulk_submit, "post", lambda e: sent.append(e) or 200)
    assert isp.main(["--send", "--submissions", str(tmp_path / "none.json")]) == 0
    assert len(sent) == 1

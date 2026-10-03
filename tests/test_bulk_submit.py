"""scripts/bulk_submit.py: CSV rows become Netlify `submission` form posts."""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bulk_submit", ROOT / "scripts" / "bulk_submit.py")
bulk_submit = importlib.util.module_from_spec(spec)
sys.modules["bulk_submit"] = bulk_submit
spec.loader.exec_module(bulk_submit)

GOOD = {
    "team_name": "Team A", "project_title": "Bus Stops", "description": "d", "solves_for": "s",
    "data_steps": "steps", "starter_project": "06-which-bus-stops-need-help",
    "repo_url": "", "demo_url": "", "large_file_url": "", "artifact_path": "",
}


def write_csv(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "entries.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=bulk_submit.COLUMNS)
        w.writeheader()
        w.writerows(rows)
    return path


def test_template_has_every_column_and_a_valid_starter():
    template = ROOT / "docs" / "bulk-load-template.csv"
    with template.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == bulk_submit.COLUMNS
        row = next(reader)
    assert row["starter_project"] in bulk_submit.starter_projects()


def test_starter_projects_are_read_from_the_real_form():
    starters = bulk_submit.starter_projects()
    assert "pitch-your-own" in starters
    assert "15-what-does-echo-see" in starters
    assert "" not in starters


def test_form_fields_match_the_site_form():
    html = bulk_submit.INDEX_HTML.read_text(encoding="utf-8")
    form = html[html.index('<form name="submission"'):]
    form = form[: form.index("</form>")]
    for name in bulk_submit.TEXT_FIELDS + ["artifact"]:
        assert f'name="{name}"' in form, name


def test_a_good_row_has_no_problems(tmp_path):
    entries = bulk_submit.read_entries(write_csv(tmp_path, [GOOD]), bulk_submit.starter_projects())
    assert [e.problems for e in entries] == [[]]


def test_bad_rows_are_reported(tmp_path):
    rows = [
        {**GOOD, "description": ""},
        {**GOOD, "starter_project": "99-nope"},
        {**GOOD, "repo_url": "http://example.com"},
        {**GOOD, "artifact_path": "missing.zip"},
    ]
    entries = bulk_submit.read_entries(write_csv(tmp_path, rows), bulk_submit.starter_projects())
    assert all(len(e.problems) == 1 for e in entries)


def test_oversized_file_is_rejected(tmp_path):
    big = tmp_path / "big.zip"
    big.write_bytes(b"0" * (bulk_submit.MAX_FILE_BYTES + 1))
    entries = bulk_submit.read_entries(
        write_csv(tmp_path, [{**GOOD, "artifact_path": "big.zip"}]), bulk_submit.starter_projects()
    )
    assert "over 8 MB" in entries[0].problems[0]


def test_multipart_body_carries_form_name_fields_and_file(tmp_path):
    z = tmp_path / "team.zip"
    z.write_bytes(b"PK\x03\x04zipbytes")
    fields = {k: v for k, v in GOOD.items() if k != "artifact_path"}
    body, ctype = bulk_submit.encode_multipart(fields, z)
    assert ctype.startswith("multipart/form-data; boundary=")
    assert b'name="form-name"\r\n\r\nsubmission' in body
    assert b'name="project_title"\r\n\r\nBus Stops' in body
    assert b'name="artifact"; filename="team.zip"' in body
    assert b"PK\x03\x04zipbytes" in body


def test_check_mode_sends_nothing_and_skips_existing(tmp_path, monkeypatch, capsys):
    rows = [GOOD, {**GOOD, "team_name": "Team B", "project_title": "New One"}]
    path = write_csv(tmp_path, rows)
    monkeypatch.setattr(bulk_submit, "existing_keys", lambda: {bulk_submit._key(" team a", "BUS  stops")})
    sent = []
    monkeypatch.setattr(bulk_submit, "post", lambda e: sent.append(e) or 200)
    assert bulk_submit.main([str(path)]) == 0
    assert sent == []
    out = capsys.readouterr().out
    assert "SKIP  row 2" in out and "READY row 3" in out

    assert bulk_submit.main([str(path), "--send"]) == 0
    assert [e.fields["team_name"] for e in sent] == ["Team B"]


def test_any_bad_row_blocks_sending(tmp_path, monkeypatch):
    path = write_csv(tmp_path, [GOOD, {**GOOD, "team_name": "Team B", "solves_for": ""}])
    monkeypatch.setattr(bulk_submit, "existing_keys", lambda: set())
    sent = []
    monkeypatch.setattr(bulk_submit, "post", lambda e: sent.append(e) or 200)
    assert bulk_submit.main([str(path), "--send"]) == 1
    assert sent == []


def test_rerun_before_sync_does_not_send_twice(tmp_path, monkeypatch, capsys):
    """The live list lags until the next sync; the local sent record covers the gap."""
    path = write_csv(tmp_path, [GOOD, {**GOOD, "team_name": "Team B", "project_title": "Two"}])
    monkeypatch.setattr(bulk_submit, "existing_keys", lambda: set())  # sync has not run
    sent = []
    monkeypatch.setattr(bulk_submit, "post", lambda e: sent.append(e.fields["team_name"]) or 200)
    assert bulk_submit.main([str(path), "--send"]) == 0
    assert bulk_submit.main([str(path), "--send"]) == 0
    assert sent == ["Team A", "Team B"]
    assert "already sent from this CSV" in capsys.readouterr().out


def test_a_failed_send_is_retried_and_successes_are_not(tmp_path, monkeypatch):
    import urllib.error
    path = write_csv(tmp_path, [GOOD, {**GOOD, "team_name": "Team B", "project_title": "Two"}])
    monkeypatch.setattr(bulk_submit, "existing_keys", lambda: set())
    calls = []

    def flaky(e):
        calls.append(e.fields["team_name"])
        if e.fields["team_name"] == "Team B" and calls.count("Team B") == 1:
            raise urllib.error.URLError("network down")
        return 200

    monkeypatch.setattr(bulk_submit, "post", flaky)
    assert bulk_submit.main([str(path), "--send"]) == 1
    assert bulk_submit.main([str(path), "--send"]) == 0
    assert calls == ["Team A", "Team B", "Team B"]


def test_the_same_project_twice_in_one_csv_is_sent_once(tmp_path, monkeypatch):
    path = write_csv(tmp_path, [GOOD, GOOD])
    monkeypatch.setattr(bulk_submit, "existing_keys", lambda: set())
    sent = []
    monkeypatch.setattr(bulk_submit, "post", lambda e: sent.append(e) or 200)
    assert bulk_submit.main([str(path), "--send"]) == 0
    assert len(sent) == 1

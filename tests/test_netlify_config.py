"""netlify.toml's build copies data/ into the publish directory as the
FALLBACK snapshot that site/scripts/data.js reads when GitHub's raw CDN is
unreachable (spec 2026-09-24 §4.3). Live data comes from GitHub; this copy
is only as fresh as the last deploy.

Ballots are no longer committed at all (§4.4), so there is nothing for the
build to strip. The guard moves to the source: no file under data/ may hold
ballot-level data, and git ignores data/ballots.json.

The build command is executed, not pattern-matched.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
NETLIFY_TOML = REPO_ROOT / "netlify.toml"


def _toml_value(key: str) -> str:
    text = NETLIFY_TOML.read_text(encoding="utf-8")
    match = re.search(rf'^\s*{key}\s*=\s*"(.*)"\s*$', text, re.MULTILINE)
    assert match, f"netlify.toml has no [build] {key}"
    return match.group(1)


def _seed_repo(root: Path) -> None:
    (root / "site").mkdir()
    (root / "site" / "index.html").write_text("<!doctype html>", encoding="utf-8")
    data = root / "data"
    (data / "results").mkdir(parents=True)
    (data / "submissions.json").write_text(json.dumps([{"id": "sub_001"}]), encoding="utf-8")
    (data / "results" / "vote.json").write_text(json.dumps({"counts": {}}), encoding="utf-8")


def _run_build(root: Path) -> subprocess.CompletedProcess:
    shell = shutil.which("bash") or shutil.which("sh")
    if not shell:
        pytest.skip("no POSIX shell available to execute the Netlify build command")
    return subprocess.run([shell, "-c", _toml_value("command")], cwd=root, capture_output=True, text=True)


def test_publish_directory_is_site():
    assert _toml_value("publish") == "site"


def test_build_publishes_the_data_snapshot(tmp_path):
    _seed_repo(tmp_path)
    result = _run_build(tmp_path)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "site" / "data" / "submissions.json").exists()
    assert (tmp_path / "site" / "data" / "results" / "vote.json").exists()


def test_build_is_idempotent_and_never_nests_site_data_data(tmp_path):
    _seed_repo(tmp_path)
    for _ in range(3):
        result = _run_build(tmp_path)
        assert result.returncode == 0, result.stderr
        assert not (tmp_path / "site" / "data" / "data").exists()
        assert (tmp_path / "site" / "data" / "submissions.json").exists()


def test_build_survives_a_missing_data_directory(tmp_path):
    (tmp_path / "site").mkdir()
    result = _run_build(tmp_path)
    assert result.returncode == 0, result.stderr


def _ballot_like(node) -> bool:
    if isinstance(node, dict):
        if "code" in node or "code_hash" in node or {"picks", "cast_at"} <= node.keys():
            return True
        return any(_ballot_like(v) for v in node.values())
    if isinstance(node, list):
        return any(_ballot_like(v) for v in node)
    return False


def test_no_committed_data_file_holds_ballot_level_data():
    offenders = [
        str(p.relative_to(REPO_ROOT))
        for p in (REPO_ROOT / "data").rglob("*.json")
        if _ballot_like(json.loads(p.read_text(encoding="utf-8")))
    ]
    assert offenders == [], f"ballot-level data committed under data/: {offenders}"


def test_ballot_detector_actually_detects():
    # Guards the guard: the scan above must not pass vacuously.
    assert _ballot_like([{"code_hash": "x", "picks": [], "cast_at": "t"}])
    assert _ballot_like({"rows": [{"picks": ["a"], "cast_at": "t"}]})
    assert not _ballot_like([{"id": "sub_001", "project_title": "x"}])


def test_git_ignores_a_stray_ballots_file():
    git = shutil.which("git")
    if not git:
        pytest.skip("git not available")
    result = subprocess.run([git, "check-ignore", "-q", "data/ballots.json"], cwd=REPO_ROOT)
    assert result.returncode == 0, "data/ballots.json is not git-ignored"

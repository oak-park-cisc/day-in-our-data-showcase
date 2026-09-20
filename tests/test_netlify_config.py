"""I2: data/ballots.json must never reach the published site.

netlify.toml's build command copies data/ into the publish directory so the
page can fetch /data/... . Copying it wholesale also published
data/ballots.json at https://<site>/data/ballots.json, with
{code_hash, picks, cast_at} for every ballot cast. Nothing on the site fetches
it; only tally.yml reads it, and it does so from the repo checkout.

The existing SHA-256 argument in _hash_code covers offline brute force of an
unspent code. It does not cover this: anyone holding a plaintext code -- the
volunteer who handed out slips, anyone who photographs the slip sheet -- can
hash it in one line and read exactly how that person voted. That is ballot
secrecy, not code recovery, and no hash strength fixes it.

The build command is executed here rather than pattern-matched, so a future
rewrite that reintroduces the leak fails this test however it is spelled.
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


def _build_command() -> str:
    text = NETLIFY_TOML.read_text(encoding="utf-8")
    match = re.search(r'^\s*command\s*=\s*"(.*)"\s*$', text, re.MULTILINE)
    assert match, "netlify.toml has no [build] command"
    return match.group(1)


def _publish_dir() -> str:
    text = NETLIFY_TOML.read_text(encoding="utf-8")
    match = re.search(r'^\s*publish\s*=\s*"(.*)"\s*$', text, re.MULTILINE)
    assert match, "netlify.toml has no [build] publish directory"
    return match.group(1)


def _seed_repo(root: Path) -> None:
    """A minimal stand-in for the repo as Netlify checks it out."""
    (root / "site").mkdir()
    (root / "site" / "index.html").write_text("<!doctype html>", encoding="utf-8")
    data = root / "data"
    data.mkdir()
    (data / "submissions.json").write_text(json.dumps([{"id": "sub_001"}]), encoding="utf-8")
    (data / "ballots.json").write_text(
        json.dumps([{"code_hash": "deadbeef", "picks": ["sub_001"], "cast_at": "2026-10-03T16:05:00Z"}]),
        encoding="utf-8",
    )
    results = data / "results"
    results.mkdir()
    (results / "vote.json").write_text(json.dumps({"counts": {}}), encoding="utf-8")


def _run_build(root: Path) -> subprocess.CompletedProcess:
    shell = shutil.which("bash") or shutil.which("sh")
    if not shell:
        pytest.skip("no POSIX shell available to execute the Netlify build command")
    return subprocess.run(
        [shell, "-c", _build_command()],
        cwd=root,
        capture_output=True,
        text=True,
    )


def test_publish_directory_is_site():
    assert _publish_dir() == "site"


def test_build_does_not_publish_ballots_json(tmp_path):
    _seed_repo(tmp_path)
    result = _run_build(tmp_path)
    assert result.returncode == 0, result.stderr

    published = tmp_path / "site" / "data" / "ballots.json"
    assert not published.exists(), (
        "data/ballots.json reached the publish directory; every ballot would be "
        "readable at https://<site>/data/ballots.json"
    )


def test_build_still_publishes_what_the_site_actually_fetches(tmp_path):
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
        assert not (tmp_path / "site" / "data" / "ballots.json").exists()
        assert (tmp_path / "site" / "data" / "submissions.json").exists()


def test_build_survives_a_missing_data_directory(tmp_path):
    # `mkdir -p data` guards the very first deploy. Removing ballots.json must
    # not turn that first deploy into a hard failure either.
    (tmp_path / "site").mkdir()
    result = _run_build(tmp_path)
    assert result.returncode == 0, result.stderr


def test_ballots_are_not_removed_from_the_repo_itself(tmp_path):
    # The tally reads data/ballots.json from the checkout; the build must
    # strip it from the COPY, never from the source.
    _seed_repo(tmp_path)
    result = _run_build(tmp_path)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "data" / "ballots.json").exists()

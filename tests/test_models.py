from pathlib import Path

from judging.models import Submission, load_submissions

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_all_fixture_submissions():
    subs = load_submissions(FIXTURES / "submissions.json")
    assert len(subs) == 6
    assert all(isinstance(s, Submission) for s in subs)


def test_anon_ids_are_unique():
    subs = load_submissions(FIXTURES / "submissions.json")
    assert len({s.anon_id for s in subs}) == len(subs)


def test_no_code_submission_is_valid():
    """A cleaned dataset with no repo is a first-class submission."""
    subs = load_submissions(FIXTURES / "submissions.json")
    no_code = next(s for s in subs if s.id == "sub_002")
    assert no_code.repo_url is None
    assert no_code.artifacts


def test_large_file_url_is_optional():
    subs = load_submissions(FIXTURES / "submissions.json")
    assert any(s.large_file_url for s in subs)
    assert any(s.large_file_url is None for s in subs)

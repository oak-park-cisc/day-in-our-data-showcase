"""I7 + M1: covering tests for the two workflow files nothing else guards.

I7 -- ci.yml ran only pytest. Nothing referenced tests/js, which is the ONLY
automated guard on the rendering layer of results.html, including the
escaping assertions that closed this project's one Critical finding. A
rendering regression would have reached main with a green tick.

M1 -- judge.yml's `mock: true` default and its use of the TYPED `inputs.mock`
context are both correct, and both guard a money path: `github.event.inputs`
yields the string "false", which is truthy in a GitHub expression, so a
dispatch with mock unchecked would have dropped `--mock` and billed ~200-300
real API calls. Nothing tested either.

Both are checked by reading the real workflow files as text -- the same
technique as tests/test_tally_workflow.py, and for the same reason: PyYAML is
not a project dependency, and there is no drift risk against a hand-copied
duplicate.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
CI = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
JUDGE = (WORKFLOWS / "judge.yml").read_text(encoding="utf-8")


# ---- I7: the JS suite runs in CI ----


def test_ci_runs_the_python_suite():
    assert re.search(r"pytest\s+tests/", CI)


def test_ci_runs_the_js_suite():
    assert "node --test" in CI, (
        "tests/js is the only automated guard on the results.html rendering "
        "layer, escaping included; CI must run it"
    )


def test_ci_uses_the_glob_form_not_the_bare_directory():
    # `node --test tests/js` fails with MODULE_NOT_FOUND on Node 24: the bare
    # directory is resolved as a module specifier, not walked for test files.
    assert "node --test tests/js/*.test.js" in CI
    assert not re.search(r"node --test tests/js\s*$", CI, re.MULTILINE)


def test_ci_sets_up_node():
    assert "actions/setup-node" in CI


def test_the_js_test_files_match_the_glob_ci_runs():
    # A test file named outside *.test.js would be silently skipped by CI.
    files = sorted(p.name for p in (REPO_ROOT / "tests" / "js").glob("*.js"))
    assert files, "expected JS tests to exist"
    assert all(name.endswith(".test.js") for name in files), files


def test_the_js_suite_header_documents_the_working_invocation():
    # The header comment used to document the broken bare-directory form.
    for path in sorted((REPO_ROOT / "tests" / "js").glob("*.test.js")):
        head = path.read_text(encoding="utf-8")[:1200]
        assert "node --test" in head, f"{path.name} should say how to run it"
        assert not re.search(r"node --test tests/js\s*$", head, re.MULTILINE), (
            f"{path.name} documents the bare-directory form, which fails on Node 24"
        )


def test_ci_still_proves_the_mock_path_never_reaches_the_network():
    assert "ANTHROPIC_API_KEY" in CI
    assert "unset" in CI  # the comment recording why it is absent


# ---- M1: nothing may quietly turn the zero-spend default off ----


def test_judge_workflow_defaults_to_the_mock_dry_run():
    mock_input = re.search(
        r"^\s*mock:\s*$(?P<body>(?:\n\s+.*)+)", JUDGE, re.MULTILINE
    )
    assert mock_input, "judge.yml must declare a `mock` workflow_dispatch input"
    body = mock_input.group("body")
    assert re.search(r"^\s*default:\s*true\s*$", body, re.MULTILINE), (
        "mock must default to true: a manual-dispatch default of false means a "
        "mis-click bills ~200-300 real API calls"
    )
    assert re.search(r"^\s*type:\s*boolean\s*$", body, re.MULTILINE), (
        "mock must be typed boolean, or `inputs.mock` is not a real boolean"
    )


def test_judge_workflow_uses_the_typed_inputs_context_not_the_string_one():
    assert "inputs.mock && '--mock' || ''" in JUDGE
    assert "github.event.inputs.mock" not in JUDGE, (
        "github.event.inputs.mock is the STRING \"false\", which is truthy in a "
        "GitHub expression: --mock would be passed when the dispatcher asked "
        "for a real run, or dropped when they did not"
    )


def test_judge_workflow_is_manual_dispatch_only():
    assert "workflow_dispatch:" in JUDGE
    assert not re.search(r"^\s*schedule:", JUDGE, re.MULTILINE), (
        "a scheduled judge run would spend real tokens unattended"
    )

import os


def test_ci_runs_without_api_credentials():
    """CI must never reach the network. If a key is present, the mock path is not being proven."""
    if os.environ.get("CI") == "true":
        assert not os.environ.get("ANTHROPIC_API_KEY"), (
            "ANTHROPIC_API_KEY is set in CI; the zero-spend guarantee is broken"
        )


def test_packages_import():
    import judging
    import voting

    assert judging is not None
    assert voting is not None

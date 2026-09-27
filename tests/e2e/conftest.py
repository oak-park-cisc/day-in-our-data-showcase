"""Browser tests for the published site.

Optional suite: it is skipped unless Playwright is installed, so the base
CI job (pip install -e ".[dev]") is unaffected. To run it:

    pip install -e ".[e2e]"
    playwright install chromium          # or set PW_CHROMIUM_PATH
    python -m pytest tests/e2e -v

The fixture below reproduces the Netlify build (netlify.toml) into a temp
directory and serves it over HTTP, so pages see the same /data/ fallback
snapshot they get in production. Requests to raw.githubusercontent.com are
blocked so the tests never depend on the network and always exercise that
fallback.
"""
from __future__ import annotations

import functools
import http.server
import os
import shutil
import threading
from pathlib import Path

import pytest

pytest.importorskip("playwright")

ROOT = Path(__file__).resolve().parents[2]

# Every page in the published site. Add a page here and it gets the load,
# layout, accessibility and link checks automatically.
PAGES = [
    "/",
    "/vote.html",
    "/results.html",
    "/start.html",
    "/where-to-code.html",
    "/cheatsheet.html",
    "/toolbox.html",
    "/workflow.html",
    "/testing.html",
]


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="session")
def site_url(tmp_path_factory):
    build = tmp_path_factory.mktemp("netlify-build")
    shutil.copytree(ROOT / "site", build, dirs_exist_ok=True)
    shutil.rmtree(build / "data", ignore_errors=True)
    shutil.copytree(ROOT / "data", build / "data")
    handler = functools.partial(_QuietHandler, directory=str(build))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    path = os.environ.get("PW_CHROMIUM_PATH")
    return {**browser_type_launch_args, **({"executable_path": path} if path else {})}


@pytest.fixture
def page(page, site_url):
    # Offline and deterministic: force data.js onto the /data/ snapshot and
    # never call out to Google Fonts during a test run.
    page.route("https://raw.githubusercontent.com/**", lambda r: r.abort())
    page.route("https://fonts.googleapis.com/**", lambda r: r.fulfill(status=200, body="", content_type="text/css"))
    page.route("https://fonts.gstatic.com/**", lambda r: r.abort())
    return page

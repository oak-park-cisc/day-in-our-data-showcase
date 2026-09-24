"""Each page must load data.js before the page script that calls fetchData().

A missing or misordered tag fails silently in the browser: fetchData is
undefined, the page's catch block runs, and the showcase shows "not
available yet" to everyone while the data is fine.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"

PAGES = {
    "index.html": "scripts/gallery.js",
    "vote.html": "scripts/vote.js",
    "results.html": "scripts/results.js",
}


def _script_srcs(html: str) -> list[str]:
    return re.findall(r'<script\s+src="([^"]+)"', html)


@pytest.mark.parametrize("page,page_script", PAGES.items())
def test_data_js_loads_before_the_page_script(page, page_script):
    srcs = _script_srcs((SITE / page).read_text(encoding="utf-8"))
    assert "scripts/data.js" in srcs, f"{page} does not load scripts/data.js"
    assert srcs.index("scripts/data.js") < srcs.index(page_script)


@pytest.mark.parametrize("script", ["gallery.js", "vote.js", "results.js"])
def test_no_page_script_fetches_data_directly(script):
    source = (SITE / "scripts" / script).read_text(encoding="utf-8")
    assert '"/data/' not in source, f"{script} still fetches /data/ directly"

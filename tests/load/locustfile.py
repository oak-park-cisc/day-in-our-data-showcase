"""Load test: a room of attendees opening the site at the same moment.

Not part of pytest. Run it against a local copy of the Netlify build, never
against production on the free plan (every request spends bandwidth):

    pip install -e ".[e2e]"
    # build the Netlify output locally and serve it
    rm -rf /tmp/diod && cp -r site /tmp/diod && cp -r data /tmp/diod/data
    (cd /tmp/diod && python -m http.server 8765) &
    locust -f tests/load/locustfile.py --host http://127.0.0.1:8765 \
        --headless -u 200 -r 50 -t 60s --csv load-results

Two visitor types, weighted to how the day actually runs: most people open
the guides at 11:00; fewer browse the showcase and vote. Each visitor loads
a page the way a browser does: the HTML plus its CSS and JS, then the JSON
the page script fetches from the /data/ snapshot.
"""
from __future__ import annotations

from locust import HttpUser, between, task

GUIDE_ASSETS = ["/styles/tokens.css", "/styles/base.css", "/styles/guides.css", "/scripts/copy.js"]
SHOWCASE_ASSETS = [
    "/styles/tokens.css", "/styles/base.css", "/styles/showcase.css",
    "/scripts/escape.js", "/scripts/data.js",
]


def _visit(client, path: str, assets: list[str], data: list[str] = ()) -> None:
    client.get(path, name=path)
    for asset in assets:
        client.get(asset, name="[assets]")
    for rel in data:
        client.get(f"/data/{rel}", name="[data]")


class GuideReader(HttpUser):
    weight = 3
    wait_time = between(2, 8)

    @task(4)
    def start_page(self):
        _visit(self.client, "/start.html", GUIDE_ASSETS)

    @task(2)
    def cheatsheet(self):
        _visit(self.client, "/cheatsheet.html", GUIDE_ASSETS)

    @task(1)
    def other_guides(self):
        for page in ("/where-to-code.html", "/toolbox.html", "/workflow.html", "/testing.html"):
            _visit(self.client, page, GUIDE_ASSETS)


class ShowcaseVisitor(HttpUser):
    weight = 1
    wait_time = between(3, 10)

    @task(3)
    def showcase(self):
        _visit(self.client, "/", SHOWCASE_ASSETS + ["/scripts/gallery.js"], ["submissions.json"])

    @task(1)
    def vote(self):
        _visit(self.client, "/vote.html", SHOWCASE_ASSETS + ["/scripts/vote.js"], ["submissions.json"])

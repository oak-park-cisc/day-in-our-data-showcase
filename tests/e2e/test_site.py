"""Every page: loads cleanly, fits a phone, passes axe, and links resolve."""
from __future__ import annotations

from urllib.parse import urljoin, urlparse

import pytest
from playwright.sync_api import expect

from .conftest import PAGES, ROOT

PHONE = {"width": 375, "height": 740}
DESKTOP = {"width": 1280, "height": 900}


def _open(page, site_url, path, viewport=DESKTOP):
    errors: list[str] = []
    failed: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: msg.type == "error" and errors.append(msg.text))
    page.on(
        "requestfailed",
        lambda req: req.url.startswith(site_url) and failed.append(req.url),
    )
    page.on(
        "response",
        lambda res: res.url.startswith(site_url) and res.status >= 400 and failed.append(f"{res.status} {res.url}"),
    )
    page.set_viewport_size(viewport)
    page.goto(site_url + path, wait_until="networkidle")
    return errors, failed


def _unexpected(failed: list[str]) -> list[str]:
    # Before judging runs, data/results/ does not exist and results.html
    # shows its "not published yet" state. Those 404s are the design.
    if (ROOT / "data" / "results").exists():
        return failed
    return [f for f in failed if "/data/results/" not in f]


def _own_errors(errors: list[str]) -> list[str]:
    # The routes in conftest abort GitHub and font requests on purpose; the
    # browser reports those as console errors. Anything else is real.
    return [e for e in errors if "net::ERR_FAILED" not in e and "Failed to load resource" not in e]


@pytest.mark.parametrize("path", PAGES)
def test_page_loads_without_errors(page, site_url, path):
    errors, failed = _open(page, site_url, path)
    assert page.locator("h1").count() >= 1 or page.locator("svg title").count() >= 1
    assert not _unexpected(failed), f"same-origin requests failed on {path}: {failed}"
    assert not _own_errors(errors), f"JavaScript errors on {path}: {errors}"


@pytest.mark.parametrize("path", PAGES)
def test_no_horizontal_scroll_on_a_phone(page, site_url, path):
    _open(page, site_url, path, PHONE)
    width = page.evaluate("document.documentElement.scrollWidth")
    assert width <= PHONE["width"], f"{path} is {width}px wide at a {PHONE['width']}px viewport"


@pytest.mark.parametrize("path", PAGES)
def test_axe_finds_no_serious_violations(page, site_url, path):
    axe_mod = pytest.importorskip("axe_playwright_python.sync_playwright")
    _open(page, site_url, path)
    results = axe_mod.Axe().run(page)
    bad = [v for v in results.response["violations"] if v["impact"] in ("serious", "critical")]
    detail = "\n".join(
        f"{v['id']} ({v['impact']}): {v['help']} -> {[n['target'] for n in v['nodes']][:3]}" for v in bad
    )
    assert not bad, f"axe violations on {path}:\n{detail}"


def test_every_internal_link_and_anchor_resolves(page, site_url):
    """Crawl every page; each same-origin href must return 200 and each
    #fragment must name an element on the target page."""
    seen_status: dict[str, int] = {}
    ids_by_page: dict[str, set[str]] = {}
    broken: list[str] = []
    request = page.context.request

    def ids_for(url: str) -> set[str]:
        if url not in ids_by_page:
            page.goto(url, wait_until="networkidle")
            ids_by_page[url] = set(page.eval_on_selector_all("[id]", "els => els.map(e => e.id)"))
        return ids_by_page[url]

    links: list[tuple[str, str]] = []
    for path in PAGES:
        page.goto(site_url + path, wait_until="networkidle")
        for href in page.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))"):
            links.append((path, href))

    for source, href in links:
        target = urljoin(site_url + source, href)
        parsed = urlparse(target)
        if not target.startswith(site_url):
            continue
        base = target.split("#")[0]
        if base not in seen_status:
            seen_status[base] = request.get(base).status
        if seen_status[base] != 200:
            broken.append(f"{source} -> {href} ({seen_status[base]})")
            continue
        if parsed.fragment and parsed.fragment not in ids_for(base):
            broken.append(f"{source} -> {href} (no element with id={parsed.fragment!r})")

    assert not broken, "broken internal links:\n" + "\n".join(broken)


def test_external_links_open_safely(page, site_url):
    for path in PAGES:
        page.goto(site_url + path)
        unsafe = page.eval_on_selector_all(
            "a[target=_blank]:not([rel~=noopener])", "els => els.map(e => e.href)"
        )
        assert not unsafe, f"{path}: target=_blank without rel=noopener: {unsafe}"


def test_copy_buttons_copy_the_code(page, site_url, context):
    context.grant_permissions(["clipboard-read", "clipboard-write"], origin=site_url)
    page.goto(site_url + "/start.html", wait_until="networkidle")
    first = page.locator(".code").first
    button = first.locator(".copy")
    assert button.is_visible()
    button.click()
    expect(button).to_have_text("Copied")  # clipboard write is async; wait for it
    copied = page.evaluate("navigator.clipboard.readText()")
    assert copied.strip() == first.locator("pre code").inner_text().strip()


def test_skip_link_is_first_tab_stop_on_guides(page, site_url):
    page.goto(site_url + "/start.html")
    page.keyboard.press("Tab")
    focused = page.evaluate("document.activeElement.textContent.trim()")
    assert focused == "Skip to content"


def test_guide_nav_marks_the_current_page(page, site_url):
    page.goto(site_url + "/toolbox.html")
    current = page.locator('.guide-nav a[aria-current="page"]')
    assert current.count() == 1
    assert current.inner_text() == "Toolbox"


def test_gallery_renders_from_the_fallback_snapshot(page, site_url):
    """GitHub is blocked in these tests, so this proves the /data/ fallback
    (the path the room takes if raw.githubusercontent.com is unreachable)."""
    page.goto(site_url + "/", wait_until="networkidle")
    gallery = page.locator("#gallery")
    gallery.wait_for()
    assert "not available" not in gallery.inner_text().lower()

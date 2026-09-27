"""Render the Get Started guide pages from TOML content.

    python scripts/build_guides.py           # write site/<slug>.html
    python scripts/build_guides.py --check   # exit 1 if any page is stale

Content lives in guides/site.toml (event settings, nav order) and
guides/pages/<slug>.toml (one file per page). This script holds no copy:
editing a guide means editing TOML, never HTML. The output is committed so
Netlify's build stays a plain file copy with no Python step.

A page file looks like:

    title = "Get started"
    nav_label = "Start"
    lede = "One sentence under the heading."

    [[sections]]
    id = "paths"
    heading = "Pick your path"

      [[sections.blocks]]
      type = "cards"
      ...

Block types, each rendered by the function in BLOCKS of the same name:

    prose     paragraphs = ["...", "..."]
    callout   tone = "tip" | "warn" | "event", title, body
    steps     items = [{title, body, code?, note?}]
    cards     items = [{title, body, tag?, link?, link_label?}]
    table     headers = [...], rows = [[...], ...], caption?
    commands  items = [{cmd, desc}], caption?
    code      code, lang?, caption?
    flow      stages = [{name, who, does, output, command?}], loop_label?
    timeline  slots = [{time, label, minutes, phase}], caption?
    pyramid   levels = [{name, body}] (top of the pyramid first)
    checklist items = ["...", "..."]

Text fields accept a small inline syntax, applied after HTML escaping:
`code`, **bold**, *italic*, and [label](https://url). {event.<key>} is replaced from
[event] in guides/site.toml before anything else.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDES = ROOT / "guides"
SITE = ROOT / "site"

# The pages that existed before the guides. Their nav is hand-written, so the
# guide pages list them explicitly to keep the two navs identical.
CORE_NAV = [("/", "Showcase"), ("/vote.html", "Vote"), ("/results.html", "Results")]
GUIDE_HOME = "start"


class ContentError(ValueError):
    """Raised for a malformed guide file, naming the file and the problem."""


# ---- text ---------------------------------------------------------------

_EVENT_REF = re.compile(r"\{event\.([a-z_]+)\}")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)([^*]+?)\*(?![\w*])")
_LINK = re.compile(r"\[([^\]]+)\]\(((?:https?://|/|#|mailto:)[^)\s]*)\)")


def substitute(text: str, event: dict[str, str]) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key not in event:
            raise ContentError(f"unknown placeholder {{event.{key}}}")
        return str(event[key])

    return _EVENT_REF.sub(repl, text)


def inline(text: str) -> str:
    """Escape, then apply `code`, **bold**, *italic* and [label](url).

    Code spans are cut out first so their contents are never read as bold or
    link syntax, then restored at the end.
    """
    codes: list[str] = []

    def stash(m: re.Match) -> str:
        codes.append(f"<code>{m.group(1)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    out = html.escape(text, quote=True)
    out = _INLINE_CODE.sub(stash, out)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _ITALIC.sub(r"<em>\1</em>", out)

    def link(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        external = url.startswith("http")
        rel = ' rel="noopener"' if external else ""
        return f'<a href="{url}"{rel}>{label}</a>'

    out = _LINK.sub(link, out)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], out)


def paras(text: str) -> str:
    """A body string may hold several paragraphs separated by blank lines."""
    chunks = [c.strip() for c in text.strip().split("\n\n") if c.strip()]
    return "".join(f"<p>{inline(' '.join(c.split()))}</p>" for c in chunks)


def code_block(code: str, caption: str = "") -> str:
    cap = f'<figcaption>{inline(caption)}</figcaption>' if caption else ""
    return (
        '<figure class="code">'
        f"{cap}"
        f'<pre tabindex="0"><code>{html.escape(code.strip())}</code></pre>'
        '<button type="button" class="copy" hidden>Copy</button>'
        "</figure>"
    )


def _req(block: dict, key: str):
    if key not in block:
        raise ContentError(f"{block.get('type')} block is missing '{key}'")
    return block[key]


# ---- blocks -------------------------------------------------------------


def prose(b: dict) -> str:
    return "".join(paras(p) for p in _req(b, "paragraphs"))


def callout(b: dict) -> str:
    tone = b.get("tone", "tip")
    if tone not in {"tip", "warn", "event"}:
        raise ContentError(f"callout tone must be tip, warn or event, not {tone!r}")
    title = f'<p class="callout__title">{inline(b["title"])}</p>' if b.get("title") else ""
    return f'<aside class="callout callout--{tone}">{title}{paras(_req(b, "body"))}</aside>'


def steps(b: dict) -> str:
    items = []
    for it in _req(b, "items"):
        body = paras(it.get("body", ""))
        code = code_block(it["code"], it.get("code_caption", "")) if it.get("code") else ""
        note = f'<p class="step__note">{inline(it["note"])}</p>' if it.get("note") else ""
        items.append(f"<li><h3>{inline(it['title'])}</h3>{body}{code}{note}</li>")
    return f'<ol class="steps">{"".join(items)}</ol>'


def cards(b: dict) -> str:
    out = []
    for it in _req(b, "items"):
        tag = f'<p class="card__tag">{inline(it["tag"])}</p>' if it.get("tag") else ""
        link = ""
        if it.get("link"):
            label = inline(it.get("link_label", "Open"))
            rel = ' rel="noopener"' if it["link"].startswith("http") else ""
            link = f'<p class="card__link"><a href="{html.escape(it["link"])}"{rel}>{label}</a></p>'
        code = code_block(it["code"]) if it.get("code") else ""
        out.append(
            f'<article class="card">{tag}<h3>{inline(it["title"])}</h3>'
            f'{paras(it.get("body", ""))}{code}{link}</article>'
        )
    return f'<div class="cards">{"".join(out)}</div>'


def table(b: dict) -> str:
    headers = _req(b, "headers")
    head = "".join(f'<th scope="col">{inline(h)}</th>' for h in headers)
    body = []
    for row in _req(b, "rows"):
        if len(row) != len(headers):
            raise ContentError(f"table row has {len(row)} cells, headers have {len(headers)}: {row[0]!r}")
        first, *rest = row
        cells = f'<th scope="row">{inline(first)}</th>' + "".join(f"<td>{inline(c)}</td>" for c in rest)
        body.append(f"<tr>{cells}</tr>")
    cap = f"<caption>{inline(b['caption'])}</caption>" if b.get("caption") else ""
    return (
        f'<div class="scroll-x" tabindex="0" role="region" aria-label="{html.escape(b.get("caption") or b.get("_section", headers[0]))}">'
        f'<table class="guide-table">{cap}<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'
    )


def commands(b: dict) -> str:
    rows = "".join(
        f'<tr><th scope="row"><code>{html.escape(it["cmd"])}</code></th><td>{inline(it["desc"])}</td></tr>'
        for it in _req(b, "items")
    )
    cap = f"<caption>{inline(b['caption'])}</caption>" if b.get("caption") else ""
    return (
        f'<div class="scroll-x" tabindex="0" role="region" aria-label="{html.escape(b.get("caption") or b.get("_section", "Commands"))}">'
        f'<table class="guide-table commands">{cap}'
        f'<thead><tr><th scope="col">Type this</th><th scope="col">What it does</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )


def code(b: dict) -> str:
    return code_block(_req(b, "code"), b.get("caption", ""))


def flow(b: dict) -> str:
    """A left-to-right process diagram that wraps to a column on phones.

    Built from list markup, not SVG, so it reflows, reads in order to a screen
    reader, and prints.
    """
    stages = []
    for i, s in enumerate(_req(b, "stages"), start=1):
        cmd = f'<p class="flow__cmd"><code>{html.escape(s["command"])}</code></p>' if s.get("command") else ""
        stages.append(
            f'<li class="flow__stage">'
            f'<p class="flow__num" aria-hidden="true">{i}</p>'
            f'<h3>{inline(s["name"])}</h3>'
            f'<p class="flow__who">{inline(s["who"])}</p>'
            f'<p>{inline(s["does"])}</p>'
            f'<p class="flow__out"><span>Output:</span> {inline(s["output"])}</p>'
            f"{cmd}</li>"
        )
    loop = f'<p class="flow__loop">{inline(b["loop_label"])}</p>' if b.get("loop_label") else ""
    label = html.escape(b.get("label", "Process diagram"))
    return f'<figure class="flow" aria-label="{label}"><ol style="--n:{len(stages)}">{"".join(stages)}</ol>{loop}</figure>'


def timeline(b: dict) -> str:
    slots = _req(b, "slots")
    bars = []
    for s in slots:
        phase = re.sub(r"[^a-z]", "", s.get("phase", "other").lower()) or "other"
        bars.append(
            f'<li class="timeline__slot timeline__slot--{phase}" style="--g:{int(s["minutes"])}">'
            f'<span class="timeline__time">{inline(s["time"])}</span>'
            f'<span class="timeline__label">{inline(s["label"])}</span></li>'
        )
    cap = f"<figcaption>{inline(b['caption'])}</figcaption>" if b.get("caption") else ""
    return f'<figure class="timeline">{cap}<ol>{"".join(bars)}</ol></figure>'


def pyramid(b: dict) -> str:
    levels = _req(b, "levels")
    n = len(levels)
    out = []
    for i, lv in enumerate(levels):
        width = 40 + 60 * i / max(n - 1, 1)
        out.append(
            f'<li style="--w:{width:.0f}%"><strong>{inline(lv["name"])}</strong>'
            f'<span>{inline(lv["body"])}</span></li>'
        )
    return f'<figure class="pyramid"><ol>{"".join(out)}</ol></figure>'


def checklist(b: dict) -> str:
    items = "".join(f"<li>{inline(i)}</li>" for i in _req(b, "items"))
    return f'<ul class="checklist">{items}</ul>'


BLOCKS = {f.__name__: f for f in (prose, callout, steps, cards, table, commands, code, flow, timeline, pyramid, checklist)}


# ---- pages --------------------------------------------------------------


def _walk_strings(node, fn):
    """Apply fn to every string in a parsed TOML tree."""
    if isinstance(node, str):
        return fn(node)
    if isinstance(node, list):
        return [_walk_strings(v, fn) for v in node]
    if isinstance(node, dict):
        return {k: _walk_strings(v, fn) for k, v in node.items()}
    return node


def load(root: Path = GUIDES) -> tuple[dict, list[tuple[str, dict]]]:
    site = tomllib.loads((root / "site.toml").read_text(encoding="utf-8"))
    event = site["event"]
    pages = []
    for slug in site["nav"]["pages"]:
        path = root / "pages" / f"{slug}.toml"
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
            pages.append((slug, _walk_strings(raw, lambda s: substitute(s, event))))
        except (ContentError, tomllib.TOMLDecodeError) as exc:
            raise ContentError(f"{path.relative_to(root.parent)}: {exc}") from exc
    return site, pages


def nav(current: str, pages: list[tuple[str, dict]]) -> str:
    items = [f'<li><a href="{href}">{label}</a></li>' for href, label in CORE_NAV]
    home_current = ' aria-current="page"' if current == GUIDE_HOME else ""
    items.append(f'<li><a href="/{GUIDE_HOME}.html"{home_current}>Get started</a></li>')
    sub = []
    for slug, page in pages:
        cur = ' aria-current="page"' if slug == current else ""
        sub.append(f'<li><a href="/{slug}.html"{cur}>{html.escape(page["nav_label"])}</a></li>')
    return (
        '<nav class="site-nav" aria-label="Site"><div class="wrap"><ul>'
        + "".join(items)
        + '</ul></div></nav>'
        + '<nav class="guide-nav" aria-label="Guides"><div class="wrap"><ul>'
        + "".join(sub)
        + "</ul></div></nav>"
    )


def render_page(slug: str, page: dict, site: dict, pages: list[tuple[str, dict]]) -> str:
    for key in ("title", "nav_label", "lede", "sections"):
        if key not in page:
            raise ContentError(f"guides/pages/{slug}.toml is missing '{key}'")
    event = site["event"]
    toc = "".join(
        f'<li><a href="#{html.escape(s["id"])}">{inline(s["heading"])}</a></li>' for s in page["sections"]
    )
    sections = []
    for s in page["sections"]:
        blocks = []
        for b in s.get("blocks", []):
            kind = b.get("type")
            if kind not in BLOCKS:
                raise ContentError(f"guides/pages/{slug}.toml: unknown block type {kind!r} in section {s['id']!r}")
            try:
                # Fallback accessible name for scrollable regions, so two
                # uncaptioned tables on one page never share a label.
                blocks.append(BLOCKS[kind]({"_section": s["heading"], **b}))
            except ContentError as exc:
                raise ContentError(f"guides/pages/{slug}.toml, section {s['id']!r}: {exc}") from exc
        intro = paras(s["intro"]) if s.get("intro") else ""
        sections.append(
            f'<section id="{html.escape(s["id"])}" class="guide-section">'
            f'<h2>{inline(s["heading"])}</h2>{intro}{"".join(blocks)}</section>'
        )
    title = html.escape(page["title"])
    desc = html.escape(" ".join(page.get("description", page["lede"]).split()))
    event_name = html.escape(event["name"])
    return f"""<!doctype html>
<!-- GENERATED by scripts/build_guides.py from guides/pages/{slug}.toml. Edit the TOML, not this file. -->
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} &middot; {event_name}</title>
  <meta name="description" content="{desc}" />
  <link rel="stylesheet" href="styles/tokens.css" />
  <link rel="stylesheet" href="styles/base.css" />
  <link rel="stylesheet" href="styles/guides.css" />
</head>
<body class="guide">
  <a class="skip-link" href="#main">Skip to content</a>
  {nav(slug, pages)}
  <header class="guide-hero">
    <div class="wrap">
      <p class="guide-hero__event">{event_name} &middot; {html.escape(event["date"])}</p>
      <h1>{title}</h1>
      <p class="guide-hero__lede">{inline(page["lede"])}</p>
    </div>
  </header>
  <main id="main" class="wrap guide-main">
    <nav class="toc" aria-label="On this page"><p>On this page</p><ol>{toc}</ol></nav>
    <div class="guide-body">
      {"".join(sections)}
    </div>
  </main>
  <footer class="guide-footer">
    <div class="wrap">
      <p>Found a mistake? These pages are built from <code>guides/pages/{slug}.toml</code> in the
      <a href="https://github.com/oak-park-cisc/day-in-our-data-showcase" rel="noopener">showcase repository</a>. Pull requests welcome.</p>
    </div>
  </footer>
  <script src="scripts/copy.js"></script>
</body>
</html>
"""


def build(root: Path = GUIDES, out: Path = SITE) -> dict[Path, str]:
    site, pages = load(root)
    return {out / f"{slug}.html": render_page(slug, page, site, pages) for slug, page in pages}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if committed HTML is stale")
    args = parser.parse_args(argv)
    try:
        rendered = build()
    except ContentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    stale = [p for p, text in rendered.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
    if args.check:
        for p in stale:
            print(f"stale: {p.relative_to(ROOT)} (run python scripts/build_guides.py)", file=sys.stderr)
        return 1 if stale else 0
    for p, text in rendered.items():
        p.write_text(text, encoding="utf-8")
    print(f"wrote {len(rendered)} pages ({len(stale)} changed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

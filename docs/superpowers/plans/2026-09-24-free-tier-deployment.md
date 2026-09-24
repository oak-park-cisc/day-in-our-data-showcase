# Free-Tier Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the showcase on Netlify's free plan without exhausting its ~20-deploy monthly budget, and stop committing ballot-level data to the now-public repo.

**Architecture:** Pages fetch `data/*.json` live from `raw.githubusercontent.com`, falling back to the same-origin `/data/` snapshot Netlify copied at the last deploy. Every bot data commit carries `[skip netlify]`, so only code changes deploy. The tally reads ballots from the Netlify Forms API in memory and commits only aggregates; sync no longer touches ballots at all.

**Tech Stack:** Python 3.11 (stdlib + pydantic/anthropic only), vanilla browser JS, `node:test` + `node:vm` (Node 22 built-ins), GitHub Actions, Netlify Forms.

**Spec:** `docs/superpowers/specs/2026-09-24-free-tier-deployment-design.md`

## Global Constraints

- Python dependencies stay exactly `anthropic>=1.0.0`, `pydantic>=2.0` (+ `pytest` dev). No PyYAML — workflow tests read YAML as text.
- JS tests use only Node built-ins; run with `node --test tests/js/*.test.js` (the glob is required).
- Python tests: `python -m pytest tests/ -v`. No test makes a real HTTP call. `ANTHROPIC_API_KEY` stays unset.
- Live data base URL, verbatim: `https://raw.githubusercontent.com/oak-park-cisc/day-in-our-data-showcase/main/data/`
- Snapshot base, verbatim: `/data/`
- Every `git commit -m` in `.github/workflows/*.yml` contains `[skip netlify]`.
- No file under `data/` may ever hold a ballot record (`code`, `code_hash`, or a record with both `picks` and `cast_at`).
- A ballot-form fetch never puts an HTTP response body into an error message (it can hold raw voter codes).
- Every participant-supplied string still goes through `escapeHtml()` before `innerHTML`; `vote.js` uses `textContent`. Rendering is out of scope — do not touch it.
- `voting/tally.py`, `voting/ranking.py`, `voting/compare.py`, `judging/` are not modified.
- Each new test is observed FAILING before its implementation (project practice).
- Commit messages end with a blank line then `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Work on branch `feat/free-tier-deployment` (already created; the spec is commit `9e64d43`).

## Review Focus

1. **Library wifi captive portal / GitHub error page** — the live URL answers `200` with an HTML body. Expect: fall back to the snapshot, not a blank page. Pinned in Task 1 (`live 200 with non-JSON body falls back`).
2. **Ballot page when data is unreachable** — `vote.js` used to call `.json()` on a 404 without checking `ok`. Expect: the "project list is not available yet" message, never a broken form. Pinned in Task 2 (`vote.test.js`).
3. **Tally dispatched before the ballot form exists on Netlify** (no deploy yet, or form detection off). Expect: one line naming the problem, exit 1, nothing written. Pinned in Task 4 (`test_netlify_failure_exits_with_one_line_and_writes_nothing`).
4. **`NETLIFY_TOKEN` secret not added before the tally is run.** Expect: one line naming the secret, exit 1. Pinned in Task 4 (`test_missing_token_exits_with_a_clear_message_using_the_real_module`).
5. **A stray `data/ballots.json` from an old checkout or local run.** Expect: git ignores it and CI fails if one is ever committed. Pinned in Task 6.

---

## File map

| File | Change | Responsibility |
|---|---|---|
| `site/scripts/data.js` | Create | `fetchData(relPath)`: live-first, snapshot fallback |
| `site/index.html`, `vote.html`, `results.html` | Modify | Load `data.js` before the page script |
| `site/scripts/gallery.js`, `vote.js`, `results.js` | Modify | Use `fetchData` instead of `fetch("/data/…")` |
| `tests/js/data.test.js`, `tests/js/vote.test.js` | Create | Unit tests for the above |
| `tests/js/results.*.test.js` (4 files) | Modify | Load `data.js` into the sandbox |
| `tests/test_site_script_order.py` | Create | Pins `data.js` load order in each page |
| `scripts/sync_netlify.py` | Modify | `sync()` drops ballots; new `fetch_ballots()` |
| `tests/test_sync_netlify.py` | Modify | Tests for both |
| `.github/workflows/tally.yml` | Modify | Ballots from Netlify, in memory |
| `tests/test_tally_workflow.py` | Modify | Stub `sync_netlify` module on `PYTHONPATH` |
| `.github/workflows/sync-submissions.yml`, `judge.yml` | Modify | No ballots; `[skip netlify]` |
| `tests/test_workflow_hygiene.py` | Create | `[skip netlify]`, no ballots file, tally env |
| `tests/test_sync_submissions_workflow.py` | Modify | Renamed step |
| `netlify.toml`, `.gitignore` | Modify | Snapshot copy; ignore ballots file |
| `tests/test_netlify_config.py` | Rewrite | Snapshot build + no ballot data in repo |
| `docs/deployment-runbook.md`, `docs/decision-log.md`, original spec | Modify | Docs |

---

### Task 1: `data.js` — live-first data loader

**Files:**
- Create: `site/scripts/data.js`
- Test: `tests/js/data.test.js`

**Interfaces:**
- Produces (browser globals, used by Task 2): `fetchData(relPath: string) -> Promise<any>`; `DATA_LIVE_BASE`, `DATA_SNAPSHOT_BASE` (strings). Declared with `function`/`var` so they are visible to later `<script>` tags and to `node:vm` sandboxes.

- [ ] **Step 1: Write the failing test**

Create `tests/js/data.test.js`:

```js
// tests/js/data.test.js
//
// Drives the real site/scripts/data.js inside a node:vm context with a fake
// fetch. Run with: node --test tests/js/*.test.js

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");
const assert = require("node:assert/strict");

const ROOT = path.resolve(__dirname, "..", "..");
const DATA_JS = fs.readFileSync(path.join(ROOT, "site/scripts/data.js"), "utf-8");

const LIVE = "https://raw.githubusercontent.com/oak-park-cisc/day-in-our-data-showcase/main/data/";

function response(status, bodyText) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => JSON.parse(bodyText),
  };
}

// routes: url -> response object, or an Error to throw (network failure).
function load(routes) {
  const calls = [];
  const sandbox = {
    fetch: async (url, options) => {
      calls.push({ url, options });
      if (!(url in routes)) throw new Error(`unexpected fetch: ${url}`);
      const r = routes[url];
      if (r instanceof Error) throw r;
      return r;
    },
  };
  vm.createContext(sandbox);
  vm.runInContext(DATA_JS, sandbox, { filename: "data.js" });
  return { sandbox, calls };
}

test("exposes the exact live and snapshot bases", () => {
  const { sandbox } = load({});
  assert.equal(sandbox.DATA_LIVE_BASE, LIVE);
  assert.equal(sandbox.DATA_SNAPSHOT_BASE, "/data/");
});

test("live success returns live data and never touches the snapshot", async () => {
  const { sandbox, calls } = load({
    [LIVE + "submissions.json"]: response(200, '[{"id":"sub_001"}]'),
  });
  const data = await sandbox.fetchData("submissions.json");
  assert.equal(data[0].id, "sub_001");
  assert.deepEqual(calls.map((c) => c.url), [LIVE + "submissions.json"]);
  assert.equal(calls[0].options.cache, "no-store");
});

test("live 429 falls back to the snapshot", async () => {
  const { sandbox, calls } = load({
    [LIVE + "results/comparison.json"]: response(429, "rate limited"),
    "/data/results/comparison.json": response(200, '{"n":3}'),
  });
  const data = await sandbox.fetchData("results/comparison.json");
  assert.equal(data.n, 3);
  assert.deepEqual(calls.map((c) => c.url), [
    LIVE + "results/comparison.json",
    "/data/results/comparison.json",
  ]);
});

test("live network error falls back to the snapshot", async () => {
  const { sandbox } = load({
    [LIVE + "submissions.json"]: new Error("offline"),
    "/data/submissions.json": response(200, "[]"),
  });
  assert.deepEqual(await sandbox.fetchData("submissions.json"), []);
});

test("live 200 with non-JSON body falls back", async () => {
  // Review Focus 1: a captive portal or error page answering 200 with HTML.
  const { sandbox } = load({
    [LIVE + "submissions.json"]: response(200, "<html>Library wifi login</html>"),
    "/data/submissions.json": response(200, '[{"id":"sub_002"}]'),
  });
  const data = await sandbox.fetchData("submissions.json");
  assert.equal(data[0].id, "sub_002");
});

test("both sources failing rejects, so the page's own fallback runs", async () => {
  const { sandbox } = load({
    [LIVE + "submissions.json"]: response(404, "nope"),
    "/data/submissions.json": response(404, "nope"),
  });
  await assert.rejects(() => sandbox.fetchData("submissions.json"));
});

for (const bad of ["../secrets.json", "/etc/passwd", "https://evil.example/x.json", "a\\b.json", ""]) {
  test(`refuses unsafe path ${JSON.stringify(bad)} without fetching`, async () => {
    const { sandbox, calls } = load({});
    await assert.rejects(() => sandbox.fetchData(bad));
    assert.equal(calls.length, 0);
  });
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/js/data.test.js`
Expected: FAIL — `ENOENT ... site/scripts/data.js`.

- [ ] **Step 3: Write minimal implementation**

Create `site/scripts/data.js`:

```js
// site/scripts/data.js
// Load before every page script. Spec: docs/superpowers/specs/
// 2026-09-24-free-tier-deployment-design.md §4.1.
//
// The site's data lives in the public repo and changes without a deploy:
// sync, judge and tally commit with [skip netlify] so Netlify's free-plan
// deploy budget is spent only on code changes. Pages therefore read data
// live from GitHub's raw CDN (~5 minute cache), and fall back to the /data/
// snapshot Netlify copied at the last deploy if that fails -- a 429 from
// GitHub's per-IP limit on shared library wifi, an outage, or a captive
// portal answering 200 with HTML. Stale beats blank.
//
// `var` and `function` (not const/let) so these are globals visible to the
// page scripts loaded after this one and to the node:vm test sandboxes.

var DATA_LIVE_BASE =
  "https://raw.githubusercontent.com/oak-park-cisc/day-in-our-data-showcase/main/data/";
var DATA_SNAPSHOT_BASE = "/data/";

// Callers pass literals; this is a tripwire against a future caller passing
// something that escapes the two fixed bases.
function dataPathIsSafe(relPath) {
  return (
    typeof relPath === "string" &&
    relPath.length > 0 &&
    !relPath.startsWith("/") &&
    !relPath.includes("..") &&
    !relPath.includes("\\") &&
    !/^[a-z][a-z0-9+.-]*:/i.test(relPath)
  );
}

async function fetchJSONFrom(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return await response.json();
}

async function fetchData(relPath) {
  if (!dataPathIsSafe(relPath)) throw new Error(`refusing data path: ${relPath}`);
  try {
    return await fetchJSONFrom(DATA_LIVE_BASE + relPath);
  } catch {
    return await fetchJSONFrom(DATA_SNAPSHOT_BASE + relPath);
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/js/data.test.js`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
git add site/scripts/data.js tests/js/data.test.js
git commit -m "feat: live-first data loader with snapshot fallback

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Pages read data through `fetchData`

**Files:**
- Modify: `site/index.html:141`, `site/vote.html:55`, `site/results.html:50` (script tags)
- Modify: `site/scripts/gallery.js:8-11`, `site/scripts/vote.js:25-27`, `site/scripts/results.js:28-32,299-303`
- Modify: `tests/js/results.abstained.test.js`, `results.caveat.test.js`, `results.render.test.js`, `results.ties.test.js`
- Create: `tests/js/vote.test.js`, `tests/test_site_script_order.py`

**Interfaces:**
- Consumes: `fetchData(relPath)` from Task 1.
- Produces: nothing new.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_site_script_order.py`:

```python
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
```

Create `tests/js/vote.test.js`:

```js
// tests/js/vote.test.js
//
// Review Focus 2: vote.js used to call response.json() without checking
// response.ok. With data unreachable the voter must see the "not available
// yet" message, and the ballot selects must not be built.

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");
const assert = require("node:assert/strict");

const ROOT = path.resolve(__dirname, "..", "..");
const ESCAPE_JS = fs.readFileSync(path.join(ROOT, "site/scripts/escape.js"), "utf-8");
const DATA_JS = fs.readFileSync(path.join(ROOT, "site/scripts/data.js"), "utf-8");
const VOTE_JS = fs.readFileSync(path.join(ROOT, "site/scripts/vote.js"), "utf-8");

function createSandbox(fetchImpl) {
  const error = { textContent: "", hidden: true };
  const selectsBuilt = [];
  const form = {
    elements: new Proxy({}, {
      get: (_t, name) => {
        selectsBuilt.push(name);
        return { innerHTML: "", appendChild() {} };
      },
    }),
    addEventListener() {},
  };
  let readyHandler = null;
  const sandbox = {
    fetch: fetchImpl,
    document: {
      getElementById: (id) => (id === "ballot-form" ? form : id === "ballot-error" ? error : null),
      createElement: () => ({}),
      addEventListener: (evt, fn) => {
        if (evt === "DOMContentLoaded") readyHandler = fn;
      },
    },
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(ESCAPE_JS, sandbox, { filename: "escape.js" });
  vm.runInContext(DATA_JS, sandbox, { filename: "data.js" });
  vm.runInContext(VOTE_JS, sandbox, { filename: "vote.js" });
  return { sandbox, error, selectsBuilt, getReady: () => readyHandler };
}

test("unreachable data shows the not-available message and builds no selects", async () => {
  const notFound = async () => ({ ok: false, status: 404, json: async () => ({ message: "Not Found" }) });
  const { sandbox, error, selectsBuilt, getReady } = createSandbox(notFound);
  await getReady()();  // vote.js registers setupBallot on DOMContentLoaded
  assert.equal(error.hidden, false);
  assert.match(error.textContent, /not available yet/);
  assert.deepEqual(selectsBuilt, []);
});
```

In each of the four `tests/js/results.*.test.js` files, make two edits:

After the `ESCAPE_JS` line, add:

```js
const DATA_JS = fs.readFileSync(path.join(ROOT, "site/scripts/data.js"), "utf-8");
```

After `vm.runInContext(ESCAPE_JS, sandbox, { filename: "escape.js" });`, add:

```js
  // data.js before results.js, as in results.html. The fixtures stay keyed
  // by /data/... on purpose: the fake fetch throws on the live GitHub URL,
  // so every load exercises fetchData's snapshot fallback path.
  vm.runInContext(DATA_JS, sandbox, { filename: "data.js" });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_site_script_order.py -v`
Expected: FAIL — 3 × "does not load scripts/data.js", 3 × "still fetches /data/ directly".

Run: `node --test tests/js/*.test.js`
Expected: `vote.test.js` FAILS (the error shown is not the not-available message, or selects were built). The four results suites still pass: data.js is loaded but not called yet.

- [ ] **Step 3: Implement**

In `site/index.html`, `site/vote.html` and `site/results.html`, add this line directly after each `<script src="scripts/escape.js"></script>`:

```html
  <script src="scripts/data.js"></script>
```

In `site/scripts/gallery.js`, update the header comment to `// Depends on site/scripts/escape.js (escapeHtml, safeUrl) and data.js (fetchData) — include both first.` and replace:

```js
    const response = await fetch("/data/submissions.json", { cache: "no-store" });
    if (!response.ok) throw new Error(String(response.status));
    submissions = await response.json();
```

with:

```js
    submissions = await fetchData("submissions.json");
```

In `site/scripts/vote.js`, add `// Depends on site/scripts/data.js (fetchData) — include it first.` as line 2, and replace:

```js
    const response = await fetch("/data/submissions.json", { cache: "no-store" });
    submissions = await response.json();
```

with:

```js
    submissions = await fetchData("submissions.json");
```

In `site/scripts/results.js`:
- Line 2 becomes `// Depends on site/scripts/escape.js (escapeHtml, safeUrl) and data.js (fetchData) — include both first.`
- In the line-7 comment, change `/data/submissions.json` to `submissions.json`.
- Delete the whole `loadJSON` function (lines 28–32).
- Replace the three `loadJSON("/data/…")` calls in `init()` with:

```js
      fetchData("submissions.json"),
      fetchData("results/bracket.json"),
      fetchData("results/comparison.json"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_site_script_order.py -v && node --test tests/js/*.test.js`
Expected: all PASS, including all four existing results suites.

- [ ] **Step 5: Commit**

```bash
git add site/ tests/js/ tests/test_site_script_order.py
git commit -m "feat: pages read data live from GitHub with snapshot fallback

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `sync_netlify.py` — sync drops ballots, `fetch_ballots()` added

**Files:**
- Modify: `scripts/sync_netlify.py` (module docstring; `_hash_code` docstring; `sync()`; `main()`; new `fetch_ballots`)
- Modify: `.gitignore`
- Test: `tests/test_sync_netlify.py`

**Interfaces:**
- Consumes: existing `resolve_form_id`, `fetch_all_submissions`, `build_ballots`, `_http_get_json`, `NetlifySyncError`, `BALLOT_FORM_NAME`.
- Produces (used by Task 4): `fetch_ballots(token: str, site_id: str | None = None, get_json: GetJSON = _http_get_json) -> list[dict]`, where each dict is `{"code_hash": str, "picks": [str, str, str], "cast_at": str}`. Raises `NetlifySyncError` on any failure, and the message never contains a ballot response body.
- `sync(token, data_dir, site_id=None, get_json=...)` keeps its signature and writes only `submissions.json` and `id_map.json`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_sync_netlify.py`:

Replace `default_urls()` with a version that omits the ballot submissions URL. The fake raises on any unexpected URL, so this alone proves `sync()` never requests ballots:

```python
def default_urls():
    return {
        f"{sync_netlify.NETLIFY_API}/forms": FORMS_PAYLOAD,
        submissions_url("form-sub-123"): SUBMISSIONS_PAYLOAD,
    }


def ballot_urls():
    return {
        f"{sync_netlify.NETLIFY_API}/forms": FORMS_PAYLOAD,
        submissions_url("form-ballot-456"): BALLOTS_PAYLOAD,
    }
```

Replace `test_sync_writes_both_files` with:

```python
def test_sync_writes_submissions_and_id_map_and_never_ballots(tmp_path):
    sync_netlify.sync(
        "test-token", tmp_path, site_id="site-abc", get_json=fake_get_json(default_urls())
    )
    assert len(json.loads((tmp_path / "submissions.json").read_text())) == 2
    assert (tmp_path / sync_netlify.ID_MAP_FILENAME).exists()
    assert not (tmp_path / "ballots.json").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["id_map.json", "submissions.json"]


def test_sync_works_before_the_ballot_form_exists(tmp_path):
    # The ballot form is detected on the first deploy of vote.html. Syncing
    # submissions must not depend on it.
    urls = default_urls()
    urls[f"{sync_netlify.NETLIFY_API}/forms"] = [FORMS_PAYLOAD[0]]
    sync_netlify.sync("test-token", tmp_path, site_id="site-abc", get_json=fake_get_json(urls))
    assert (tmp_path / "submissions.json").exists()


def test_fetch_ballots_returns_hashed_ballots_in_tally_shape():
    ballots = sync_netlify.fetch_ballots(
        "test-token", site_id="site-abc", get_json=fake_get_json(ballot_urls())
    )
    assert ballots == [{
        "code_hash": hashlib.sha256(b"ABCDEFGHJ2").hexdigest(),
        "picks": ["sub_001", "sub_002", "sub_003"],
        "cast_at": "2026-10-03T16:05:00.000Z",
    }]


def test_fetch_ballots_follows_pagination():
    one = BALLOTS_PAYLOAD[0]
    urls = {
        f"{sync_netlify.NETLIFY_API}/forms": FORMS_PAYLOAD,
        submissions_url("form-ballot-456", 1): [one] * sync_netlify.PAGE_SIZE,
        submissions_url("form-ballot-456", 2): [one],
    }
    ballots = sync_netlify.fetch_ballots("test-token", site_id="site-abc", get_json=fake_get_json(urls))
    assert len(ballots) == sync_netlify.PAGE_SIZE + 1


def test_fetch_ballots_raises_when_the_ballot_form_is_missing():
    urls = {f"{sync_netlify.NETLIFY_API}/forms": [FORMS_PAYLOAD[0]]}
    with pytest.raises(sync_netlify.NetlifySyncError, match="ballot"):
        sync_netlify.fetch_ballots("test-token", site_id="site-abc", get_json=fake_get_json(urls))


def test_fetch_ballots_with_no_ballots_cast_returns_empty_list():
    urls = {
        f"{sync_netlify.NETLIFY_API}/forms": FORMS_PAYLOAD,
        submissions_url("form-ballot-456"): [],
    }
    assert sync_netlify.fetch_ballots("test-token", site_id="site-abc", get_json=fake_get_json(urls)) == []
```

Rewrite `test_sync_never_leaks_a_raw_ballot_code_when_the_ballot_submissions_fetch_fails` as `test_fetch_ballots_never_leaks_a_raw_ballot_code_when_the_fetch_fails`. Keep the same docstring intent and the same `fake_urlopen`, but drop the `form-sub-123` branch and replace the call and assertions with:

```python
    with pytest.raises(sync_netlify.NetlifySyncError) as excinfo:
        sync_netlify.fetch_ballots("test-token", site_id="site-abc")  # real _http_get_json

    assert raw_code not in str(excinfo.value)
```

In `test_sync_forms_listing_error_may_include_its_body`, and in any other test still using `default_urls()`, check that nothing requests `form-ballot-456`. With the new `default_urls()` they fail loudly if something does.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_sync_netlify.py -v`
Expected: FAIL. The `sync` tests fail with `unexpected URL requested: …form-ballot-456…`, and the `fetch_ballots` tests fail with `AttributeError: module 'sync_netlify' has no attribute 'fetch_ballots'`.

- [ ] **Step 3: Implement**

In `scripts/sync_netlify.py`:

Replace the first paragraph of the module docstring with:

```python
"""Pull submitted projects from Netlify Forms into data/, and read ballots for the tally.

Run by .github/workflows/sync-submissions.yml (schedule + workflow_dispatch).
Requires NETLIFY_TOKEN (a Personal Access Token with access to the site) in
the environment. Writes data/submissions.json (the public §4.1 Submission
shape) and data/id_map.json.

Ballots are NEVER written to disk. tally.yml calls fetch_ballots() and holds
them in memory only (spec 2026-09-24-free-tier-deployment-design.md §4.4):
the repo is public, and a committed ballot file lets anyone holding a slip
code read how that person voted.
```

Replace the `sync()` ballot lines. The body becomes:

```python
    forms = get_json(f"{NETLIFY_API}/forms", token, include_body_in_errors=True)
    submission_form_id = resolve_form_id(forms, SUBMISSION_FORM_NAME, site_id)

    raw_submissions = fetch_all_submissions(get_json, submission_form_id, token)

    # The committed map is what makes sub_NNN survive a deleted submission.
    # It is read before anything is written and written back merged, never
    # pruned.
    numbers = assign_public_numbers(raw_submissions, load_id_map(data_dir / ID_MAP_FILENAME))
    submissions = build_submissions(raw_submissions, numbers)

    _write_json(data_dir / ID_MAP_FILENAME, numbers)
    _write_json(data_dir / "submissions.json", submissions)
```

Update `sync()`'s docstring: it now makes a single `/submissions` fetch, for the submission form, and that fetch does not opt into body-in-errors.

Add after `build_ballots`:

```python
def fetch_ballots(token: str, site_id: str | None = None, get_json: GetJSON = _http_get_json) -> list[dict]:
    """Every cast ballot, hashed, for tally.yml to hold in memory. Never written.

    Only the /forms listing opts into include_body_in_errors (it carries no
    voter data). The ballot /submissions fetch takes _http_get_json's safe
    default, because its error body can echo a voter's raw code.
    """
    forms = get_json(f"{NETLIFY_API}/forms", token, include_body_in_errors=True)
    ballot_form_id = resolve_form_id(forms, BALLOT_FORM_NAME, site_id)
    return build_ballots(fetch_all_submissions(get_json, ballot_form_id, token))
```

Replace `_hash_code`'s docstring with:

```python
    """One-way hash a ballot code so the tally compares hashes, not codes.

    tally.yml hashes every BALLOT_CODES entry with this same normalisation and
    compares for equality; voting/tally.py never copies a code into its
    result. Ballots are held in memory by tally.yml and never written to the
    repo or the site (spec 2026-09-24 §4.4), which is what protects ballot
    secrecy. The hash is not a secrecy mechanism and makes no claim to be one.
    """
```

In `main()`, the final print becomes:

```python
    print(f"Wrote {args.data_dir / 'submissions.json'} and {args.data_dir / ID_MAP_FILENAME}")
```

In `.gitignore`, append:

```
# Ballots are never committed; tally.yml holds them in memory (spec 2026-09-24 §4.4).
data/ballots.json
```

- [ ] **Step 4: Run tests to verify they pass**

Also update `tests/test_sync_pagination.py`, where three tests encode the old behaviour:
- `test_every_page_of_ballots_is_fetched`: replace the `sync(...)` call and file read with `ballots = sync_netlify.fetch_ballots("test-token", site_id=None, get_json=api)`. Keep both assertions (150 ballots, 150 distinct hashes).
- `test_an_empty_form_stops_after_one_request`: change the expected requests to `[("submissions", 1)]`, since `sync()` no longer asks for ballots.
- `test_a_failed_ballot_page_leaves_submissions_untouched`: the scenario no longer exists for `sync()`. Rewrite it as `test_a_failed_ballot_page_raises_from_fetch_ballots`. Set `api.fail_on = ("ballots", 2)` with 150 ballots, and assert that `fetch_ballots("test-token", site_id=None, get_json=api)` raises `NetlifySyncError`.
- In `test_a_failed_later_page_aborts_the_whole_sync_and_writes_nothing`, keep the `ballots.json` absence assertion. It is still true.

Run: `python -m pytest tests/test_sync_netlify.py tests/test_sync_pagination.py tests/test_sync_stable_ids.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/sync_netlify.py tests/test_sync_*.py .gitignore
git commit -m "feat: sync stops writing ballots; fetch_ballots reads them for the tally

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `tally.yml` reads ballots from Netlify, in memory

**Files:**
- Modify: `.github/workflows/tally.yml` (header comment lines 1–9; tally step `env:` and heredoc lines 24–71)
- Test: `tests/test_tally_workflow.py`

**Interfaces:**
- Consumes: `fetch_ballots`, `NetlifySyncError` from `scripts/sync_netlify.py` (Task 3), imported as the top-level module `sync_netlify` via `PYTHONPATH: scripts`.
- Produces: `data/results/vote.json` and `comparison.json`, the same shapes as today.

- [ ] **Step 1: Write the failing tests**

In `tests/test_tally_workflow.py`, update the module docstring's first paragraph. Ballots now come from `sync_netlify.fetch_ballots()`, and the tests put a stub `sync_netlify` module first on `PYTHONPATH`, so no HTTP call is made and there is no test hook in the shipped workflow. Then replace `_run_script` and add the stub:

```python
STUB_SYNC_NETLIFY = '''
import json, os

class NetlifySyncError(RuntimeError):
    pass

def fetch_ballots(token, site_id=None):
    if token != "test-token":
        raise AssertionError(f"stub got token {token!r}")
    failure = os.environ.get("STUB_FAIL")
    if failure:
        raise NetlifySyncError(failure)
    path = os.environ["STUB_BALLOTS_FILE"]
    return json.load(open(path)) if os.path.exists(path) else []
'''


def _run_script(cwd: Path, codes: str = DEFAULT_CODES, *, token: str | None = "test-token",
                real_module: bool = False, fail: str | None = None) -> subprocess.CompletedProcess:
    script = _extract_tally_script()
    script_path = cwd / "_extracted_tally.py"
    script_path.write_text(script, encoding="utf-8")
    stub_dir = cwd / "_stub"
    stub_dir.mkdir(exist_ok=True)
    (stub_dir / "sync_netlify.py").write_text(STUB_SYNC_NETLIFY, encoding="utf-8")
    first = REPO_ROOT / "scripts" if real_module else stub_dir
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(first), str(REPO_ROOT)])
    env["BALLOT_CODES"] = codes
    env["STUB_BALLOTS_FILE"] = str(cwd / "stub_ballots.json")
    env.pop("NETLIFY_SITE_ID", None)
    env.pop("STUB_FAIL", None)
    if fail:
        env["STUB_FAIL"] = fail
    if token is None:
        env.pop("NETLIFY_TOKEN", None)
    else:
        env["NETLIFY_TOKEN"] = token
    return subprocess.run(
        [sys.executable, str(script_path)], cwd=cwd, env=env, capture_output=True, text=True,
    )
```

In every fixture helper (`_write_fixture_data`, `_write_tied_fixture_data`, `_write_first_place_tie_fixture_data`, `_write_below_floor_fixture`, and any other), change
`(data_dir / "ballots.json").write_text(` → `(data_dir.parent / "stub_ballots.json").write_text(`.

Replace the three `test_exits_nonzero_…_missing` tests with:

```python
def test_exits_nonzero_with_a_clear_message_when_submissions_missing(tmp_path):
    result = _run_script(tmp_path)
    assert result.returncode == 1
    assert "data/submissions.json" in result.stderr
    assert "sync-submissions.yml" in result.stderr
    assert "Traceback" not in result.stderr


def test_missing_token_exits_with_a_clear_message_using_the_real_module(tmp_path):
    # Review Focus 4. Uses the REAL scripts/sync_netlify.py, which also proves
    # the heredoc's import resolves with PYTHONPATH=scripts as tally.yml sets it.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "submissions.json").write_text("[]", encoding="utf-8")
    result = _run_script(tmp_path, token=None, real_module=True)
    assert result.returncode == 1
    assert "NETLIFY_TOKEN" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (data_dir / "results").exists()


def test_netlify_failure_exits_with_one_line_and_writes_nothing(tmp_path):
    # Review Focus 3: e.g. the ballot form was never detected on Netlify.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "submissions.json").write_text("[]", encoding="utf-8")
    result = _run_script(tmp_path, fail="No Netlify form named 'ballot' found.")
    assert result.returncode == 1
    assert "No Netlify form named 'ballot' found." in result.stderr
    assert "Traceback" not in result.stderr
    assert not (data_dir / "results").exists()


def test_no_ballots_cast_publishes_zero_counts_with_the_caveat(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "submissions.json").write_text(
        json.dumps([{"id": "sub_001", "anon_id": "P-01"}]), encoding="utf-8"
    )
    result = _run_script(tmp_path)
    assert result.returncode == 0, result.stderr
    vote = json.loads((data_dir / "results" / "vote.json").read_text())
    assert vote["valid"] == 0
    assert vote["indicative"] is True


def test_tally_writes_no_ballot_level_data(tmp_path):
    _write_fixture_data(tmp_path / "data")
    assert _run_script(tmp_path).returncode == 0
    for path in (tmp_path / "data").rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "code_hash" not in text, path
        assert '"cast_at"' not in text, path
    assert not (tmp_path / "data" / "ballots.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_tally_workflow.py -v`
Expected: FAIL. The fixture tests fail because the script still reads `data/ballots.json`, and the token and Netlify-failure tests fail because there is no such check yet.

- [ ] **Step 3: Implement**

In `.github/workflows/tally.yml`, rewrite the header comment (lines 1–9) to say this: ballots are read from Netlify Forms at tally time and held in memory; only aggregates are committed; `BALLOT_CODES` validates them; see spec 2026-09-24 §4.6.

Give the tally step this `env:` block:

```yaml
        env:
          BALLOT_CODES: ${{ secrets.BALLOT_CODES }}
          NETLIFY_TOKEN: ${{ secrets.NETLIFY_TOKEN }}
          NETLIFY_SITE_ID: ${{ secrets.NETLIFY_SITE_ID }}
          # Makes scripts/sync_netlify.py importable as `sync_netlify`.
          PYTHONPATH: scripts
```

In the heredoc, add `from sync_netlify import NetlifySyncError, fetch_ballots` after the `voting` imports. Then replace everything from the `# Both files are written by sync-submissions.yml` comment through the end of the `ballots = [...]` comprehension with:

```python
          # submissions.json is written by sync-submissions.yml. Fail with one
          # clear line naming the fix rather than a FileNotFoundError traceback.
          if not Path("data/submissions.json").exists():
              print(
                  "tally.yml: missing data/submissions.json. "
                  "Run the 'Sync Netlify submissions' workflow (sync-submissions.yml) "
                  "at least once before dispatching tally.yml.",
                  file=sys.stderr,
              )
              sys.exit(1)

          submissions = json.loads(Path("data/submissions.json").read_text())
          known_ids = {s["id"] for s in submissions}
          id_of = {s["anon_id"]: s["id"] for s in submissions}

          # Ballots come straight from Netlify Forms and live only in this
          # process. They are never written: the repo is public, and a ballot
          # file lets anyone holding a slip code read that person's picks.
          token = os.environ.get("NETLIFY_TOKEN")
          if not token:
              print(
                  "tally.yml: NETLIFY_TOKEN is not set. The tally reads ballots from "
                  "Netlify Forms; add the NETLIFY_TOKEN repository secret.",
                  file=sys.stderr,
              )
              sys.exit(1)
          try:
              raw_ballots = fetch_ballots(token, os.environ.get("NETLIFY_SITE_ID") or None)
          except NetlifySyncError as exc:
              # NetlifySyncError messages never carry a ballot response body.
              print(f"tally.yml: could not read ballots from Netlify: {exc}", file=sys.stderr)
              sys.exit(1)

          ballots = [
              Ballot(
                  code=b["code_hash"],
                  picks=b["picks"],
                  cast_at=datetime.fromisoformat(b["cast_at"].replace("Z", "+00:00")),
              )
              for b in raw_ballots
          ]
```

Leave the rest of the heredoc unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_tally_workflow.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/tally.yml tests/test_tally_workflow.py
git commit -m "feat: tally reads ballots from Netlify in memory, commits only aggregates

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Workflows — `[skip netlify]`, no ballots file anywhere

**Files:**
- Modify: `.github/workflows/sync-submissions.yml:20,39-40`, `judge.yml:44`, `tally.yml:123`
- Create: `tests/test_workflow_hygiene.py`
- Modify: `tests/test_sync_submissions_workflow.py` (step-name literal)

**Interfaces:** none.

- [ ] **Step 1: Write the failing test**

Create `tests/test_workflow_hygiene.py`:

```python
"""Cross-workflow invariants (spec 2026-09-24 §4.5–4.7).

1. Every bot commit carries [skip netlify]. Netlify's free plan allows ~20
   deploys a month and pauses the site at the cap; data commits must never
   spend one. Pages read data live from GitHub instead.
2. No workflow reads or stages data/ballots.json. Ballots live only in the
   tally's memory.

Text checks, no YAML parser (not a project dependency).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = sorted((Path(__file__).resolve().parent.parent / ".github" / "workflows").glob("*.yml"))


def _commit_lines() -> list[tuple[str, str]]:
    found = []
    for wf in WORKFLOWS:
        for line in wf.read_text(encoding="utf-8").splitlines():
            if re.search(r"git commit\b", line):
                found.append((wf.name, line.strip()))
    return found


def test_the_three_data_workflows_commit():
    names = {name for name, _ in _commit_lines()}
    assert {"sync-submissions.yml", "judge.yml", "tally.yml"} <= names


@pytest.mark.parametrize("workflow,line", _commit_lines())
def test_every_bot_commit_skips_netlify(workflow, line):
    assert "[skip netlify]" in line, f"{workflow}: {line}"


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_no_workflow_touches_a_ballots_file(wf):
    assert "ballots.json" not in wf.read_text(encoding="utf-8")
```

In `tests/test_sync_submissions_workflow.py`, change the step-name literal in `_sync_step_lines()` to `"- name: Sync submissions from Netlify Forms"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_workflow_hygiene.py tests/test_sync_submissions_workflow.py -v`
Expected: FAIL. Three commit lines lack `[skip netlify]`, `sync-submissions.yml` contains `ballots.json`, and the step-name lookup raises `StopIteration`.

- [ ] **Step 3: Implement**

`sync-submissions.yml`:
- Rename the step to `- name: Sync submissions from Netlify Forms`.
- Change `git add data/submissions.json data/ballots.json data/id_map.json` to `git add data/submissions.json data/id_map.json`.
- Change the commit message to `git diff --staged --quiet || git commit -m "chore: sync submissions from Netlify [skip netlify]"`.
- Above the `git add`, add the comment `# [skip netlify]: pages read data live from GitHub; data commits must not spend the free plan's ~20 monthly deploys.`
- Change the workflow `name:` on line 1 to `Sync Netlify submissions` (unchanged if it already is; `tally.yml`'s error message names it).

`judge.yml`: change the commit line to `git diff --staged --quiet || git commit -m "chore: publish AI panel results [skip netlify]"`.

`tally.yml`: change the commit line to `git diff --staged --quiet || git commit -m "chore: publish participant vote tally [skip netlify]"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ tests/test_workflow_hygiene.py tests/test_sync_submissions_workflow.py
git commit -m "ci: data commits skip Netlify deploys; no workflow touches ballots

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `netlify.toml` snapshot build, and no ballot data in the repo

**Files:**
- Modify: `netlify.toml`
- Rewrite: `tests/test_netlify_config.py`

**Interfaces:** none.

- [ ] **Step 1: Write the failing test**

Replace `tests/test_netlify_config.py` entirely:

```python
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
```

- [ ] **Step 2: Run tests to verify the right one fails**

Run: `python -m pytest tests/test_netlify_config.py -v`
Expected: all pass except that `netlify.toml` still carries the `rm -f site/data/ballots.json` clause, which this suite doesn't check. To see the new guard fail as project practice requires, temporarily create `data/ballots.json` containing `[{"code_hash":"x","picks":[],"cast_at":"t"}]`. Confirm `test_no_committed_data_file_holds_ballot_level_data` FAILS, then delete the file. Also confirm `test_git_ignores_a_stray_ballots_file` fails with the `.gitignore` line temporarily commented out, then restore the line.

- [ ] **Step 3: Implement**

Replace `netlify.toml` with:

```toml
# Netlify build config (spec docs/superpowers/specs/2026-09-24-free-tier-deployment-design.md).
#
# Pages read data/ LIVE from raw.githubusercontent.com (site/scripts/data.js),
# because data commits carry [skip netlify] and never deploy -- the free plan
# allows ~20 deploys a month and pauses the site at the cap. The copy below is
# the FALLBACK snapshot data.js reads if GitHub is unreachable; it is as fresh
# as the last deploy.
#
# `rm -rf site/data` first: a bare `cp -r data site/data` nests site/data/data
# once site/data exists. `mkdir -p data` keeps a first deploy from failing on
# a missing source directory.
#
# No ballot data is ever under data/ (tally.yml holds ballots in memory), so
# nothing needs stripping. tests/test_netlify_config.py pins that at the source.
[build]
  publish = "site"
  command = "mkdir -p data && rm -rf site/data && cp -r data site/data"

[[headers]]
  for = "/*"
  [headers.values]
    X-Frame-Options = "DENY"
    X-Content-Type-Options = "nosniff"
    Referrer-Policy = "strict-origin-when-cross-origin"
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/ -v && node --test tests/js/*.test.js`
Expected: all PASS. Then run `git status`: `data/ballots.json` must not be present.

- [ ] **Step 5: Commit**

```bash
git add netlify.toml tests/test_netlify_config.py
git commit -m "build: data copy becomes the fallback snapshot; guard ballots at the source

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Runbook, decision log, spec amendment

**Files:**
- Rewrite: `docs/deployment-runbook.md`
- Modify: `docs/decision-log.md` (header count; append #35, #36)
- Modify: `docs/superpowers/specs/2026-09-19-day-in-our-data-showcase-design.md` (append an amendment note at the end of §3)

**Interfaces:** none. Docs only; the verification is the full test run plus a read-through.

- [ ] **Step 1: Rewrite `docs/deployment-runbook.md`**

Replace the whole file with the following text, word for word:

````markdown
# Deployment runbook

Everything needed to take this repository from merged code to a live site on
Netlify's **free** plan, accepting submissions and ballots. Written for the repo
owner; no prior context assumed. Design: `docs/superpowers/specs/2026-09-24-free-tier-deployment-design.md`.

## How the free plan is kept free

- The repo is **public**. Netlify's free plan cannot deploy a private,
  organization-owned repo.
- Netlify's free plan allows about **20 deploys a month** and pauses the site at
  the cap. So the bots (sync, judge, tally) commit with `[skip netlify]` and never
  deploy. Only commits that change the site's code deploy.
- Pages read their data **live from GitHub** (`raw.githubusercontent.com`, ~5
  minute cache). If GitHub is unreachable they fall back to the copy Netlify
  published at the last deploy.
- **Ballots are never committed.** The tally reads them from Netlify Forms and
  keeps them in memory. They remain visible in Netlify → Forms → ballot, to
  account holders only.

---

## 1. Connect the Netlify site

1. Netlify → **Add new site** → **Import an existing project** → select
   `oak-park-cisc/day-in-our-data-showcase`, branch **`main`**, on the **Free** plan.
2. Confirm the settings match `netlify.toml`: publish directory `site`, build
   command `mkdir -p data && rm -rf site/data && cp -r data site/data`.
3. Site settings → **Forms** → confirm form detection is enabled.
4. Deploy once. Submit one test entry through the submission form and confirm it
   appears under Site → Forms → submission.

## 2. Generate the ballot codes — offline

```
python -m voting.generate_codes --count <N>
```

Run it on a machine that will not commit its output. It prints the slip sheet and
the comma-joined string for the `BALLOT_CODES` secret. **Never paste the codes
into a file in this repository.** It is public.

## 3. Add the repository secrets

GitHub repo → Settings → Secrets and variables → Actions.

| Secret | Required | Used by |
|---|---|---|
| `NETLIFY_TOKEN` | yes | `sync-submissions.yml` **and `tally.yml`** (the tally reads ballots from Netlify) |
| `BALLOT_CODES` | yes | `tally.yml` |
| `ANTHROPIC_API_KEY` | only for the real judging run | `judge.yml` with `mock` unticked |
| `NETLIFY_SITE_ID` | only if needed | Set it only if a run fails with "Multiple Netlify forms named ... found" |

## 4. Verify the pipeline before the event

**Sync.** Actions → "Sync Netlify submissions" → Run workflow. Confirm it commits
`data/submissions.json` and `data/id_map.json`, and then check two things:
- Netlify → Deploys shows **no new deploy** for that commit (`[skip netlify]` is
  honoured).
- Within ~5 minutes the test entry appears in the gallery on the live site.

**Judging dry run.** Actions → "Run AI judging panel" → Run workflow, leaving
`mock` at its default `true`. Zero API spend. Confirm `results.html` shows the
bracket within ~5 minutes, again with no new deploy.

**Tally.** Visit `vote.html`, cast one ballot with a code from your slip sheet,
then Actions → `tally.yml` → Run workflow. It needs `data/submissions.json` and
the `NETLIFY_TOKEN` secret, and it fails with one clear line if either is missing.

## 5. Custom domain (optional)

Your DNS is on Cloudflare, on an account that also runs other sites. This adds
**one** record and changes nothing that exists.

1. Netlify → Domain management → **Add a domain** → `<subdomain>.<your-domain>`.
2. Cloudflare → your domain → DNS → **Add record**: type `CNAME`, name
   `<subdomain>`, target `<your-site>.netlify.app`, proxy status **DNS only**
   (grey cloud). Do not proxy it: Netlify needs to issue its own certificate.
3. Wait for Netlify to show the certificate as provisioned (minutes, occasionally
   longer).

No deploy is needed for this.

## 6. During and after the event

`sync-submissions.yml` runs every 15 minutes on Saturdays 16:00–21:59 UTC
(11:00 a.m.–4:59 p.m. Central) and on demand. New projects show on the site
within ~5 minutes of each sync.

After voting closes:
1. Run `judge.yml` with **`mock` unticked**. This is the only step that spends
   money, roughly $2 at `claude-sonnet-5` for a 20-project event.
2. Run `tally.yml`.
3. Netlify → Deploys → **Trigger deploy** once, so the fallback snapshot matches
   the published result.

## 7. Teardown — order matters

When the site is retired, **delete the Cloudflare CNAME first, then the Netlify
site.** A CNAME left pointing at a deleted Netlify site can be claimed by someone
else, who could then serve their content under your domain.

## Optional: protect `main`

Public repos get branch protection for free: Settings → Branches → add a rule for
`main` requiring a pull request. The bots push directly to `main`, so if you
enable this, allow GitHub Actions to bypass it, or they will fail.

---

## Checks that could not be made without a live site

These are tested against fakes only. One real sync clears the first three.

- **`created_at`** is assumed to be the Netlify submission timestamp field.
- **Artifact upload field shape**: the sync accepts both a URL string and
  `{url, filename, size}`.
- **Pagination**: pages until a short page returns.
- **`results.html` tie chips and notices** have never been seen rendered. On a
  low-turnout run most projects tie at zero, so many rows carry a "tied" chip;
  check that it reads well.

## Two things to know before you run this for real

**Never delete a Netlify form submission after the showcase publishes.** Public
ids are held stable by `data/id_map.json`, but don't rely on that if the map is
ever lost.

**One winner, no gift cards** (spec §1.2, amended 2026-09-21). A tie for first is
published as a shared win. The cut is `voting.ranking.DEFAULT_AWARD_COUNT`, now `1`.
````

- [ ] **Step 2: Update `docs/decision-log.md`**

Change the header line `33 decisions, in the order they were made.` to `36 decisions, in the order they were made.` Then append:

```markdown

**35.** **Owner decision.** Ballots never enter the repo. Supersedes #33's premise. The owner made the repo public on 2026-09-24 so Netlify's free plan could deploy it (the free plan cannot deploy a private, org-owned repo). #33 accepted a committed `data/ballots.json` on the grounds that ballot secrecy rests on codes staying on the slips; with the repo public, that file lets any slip-holder read a named voter's picks, and nothing requires it to exist. `sync-submissions.yml` no longer fetches ballots; `tally.yml` reads them from the Netlify Forms API via `fetch_ballots()`, holds them in memory, and commits only `vote.json` and `comparison.json`. `.gitignore` and `tests/test_netlify_config.py` guard against a stray ballot file. Plain SHA-256 stays, now for comparison only, not secrecy. Cost if wrong: ballots can't be audited from the repo; they remain in Netlify's dashboard.

**36.** **Owner decision.** Stay on Netlify's free plan, with data read live from GitHub. Free is 300 credits a month at 15 per deploy (about 20 deploys) with a hard pause at the cap, and every bot data commit used to rebuild the site. Now bot commits carry `[skip netlify]` and pages fetch `data/*.json` from `raw.githubusercontent.com`, falling back to the deploy-time snapshot on failure (GitHub allows about 5,000 unauthenticated requests per hour per IP, and a library's wifi is one IP). Moving to Cloudflare Pages or GitHub Pages was rejected nine days before the event: Netlify Forms carries submissions, uploads and ballots with no backend of ours, and replacing it means new vote-handling code on a deadline. The owner's own domain is added as a single DNS-only CNAME; teardown deletes the CNAME before the Netlify site to prevent takeover. Cost if wrong: up to ~5 minutes of display lag behind each data commit.
```

- [ ] **Step 3: Amend the original spec**

At the end of §3 in `docs/superpowers/specs/2026-09-19-day-in-our-data-showcase-design.md` (just before `## 4. Data contracts`), append:

```markdown

> **Amendment (2026-09-24) — free-tier deployment.** The repo is public. Pages read `data/` live from GitHub with a deploy-time snapshot fallback; bot commits carry `[skip netlify]`; ballots are read by the tally from Netlify Forms in memory and never committed. The text above is left as originally approved. See `2026-09-24-free-tier-deployment-design.md` and decision-log #35–#36.
```

- [ ] **Step 4: Verify**

Run: `python -m pytest tests/ -v && node --test tests/js/*.test.js`
Expected: all PASS.

Run: `git grep -n "ballots.json" -- . ':!docs/superpowers' ':!docs/decision-log.md' ':!docs/notes'`
Expected: matches only in `.gitignore`, in test assertions that it is absent, and in comments that say it is never written. No workflow, script or site file reads or writes it.

- [ ] **Step 5: Commit**

```bash
git add docs/
git commit -m "docs: free-tier runbook, decisions #35-#36, spec amendment

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## After all tasks

Push `feat/free-tier-deployment`, open a PR to `main`, and confirm CI passes. Merging the PR is the Netlify site's first deploy source, so merge only after the whole-branch review.

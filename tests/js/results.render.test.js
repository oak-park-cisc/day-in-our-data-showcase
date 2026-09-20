// tests/js/results.render.test.js
//
// Browser automation was unavailable for verifying site/results.html directly
// (see task-15-report.md), so this drives site/scripts/results.js against a
// fake DOM + fetch inside a Node vm context and asserts on the produced
// innerHTML strings. This is the same technique used to prove the XSS fix on
// gallery.js/vote.js (commit 836c6b9): it runs the real, unmodified script —
// no test-only exports, no duplicated logic — and inspects what it writes.
//
// Run with: node --test tests/js

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");
const assert = require("node:assert/strict");

const ROOT = path.resolve(__dirname, "..", "..");
const ESCAPE_JS = fs.readFileSync(path.join(ROOT, "site/scripts/escape.js"), "utf-8");
const RESULTS_JS = fs.readFileSync(path.join(ROOT, "site/scripts/results.js"), "utf-8");

function makeElement(id) {
  return {
    id,
    _html: "",
    hidden: false,
    _attrs: {},
    get innerHTML() {
      return this._html;
    },
    set innerHTML(value) {
      this._html = value;
    },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(this._attrs, name) ? this._attrs[name] : null;
    },
    setAttribute(name, value) {
      this._attrs[name] = String(value);
    },
    addEventListener() {},
    // The fake DOM stores innerHTML as an opaque string rather than parsing
    // it into a real node tree, so it can't locate real <button> children.
    // attachToggles() degrades to a no-op here; toggleDetails() is exercised
    // directly (see "toggle logic" below) against plain mock nodes instead.
    querySelectorAll() {
      return [];
    },
  };
}

// Loads escape.js and results.js into a fresh V8 context per call, wired to
// a fake document + fetch, and returns the elements map plus the captured
// DOMContentLoaded handler. Mirrors two <script> tags sharing one `window`.
function createSandbox(fetchImpl) {
  const elements = {};
  const getElement = (id) => {
    if (!elements[id]) elements[id] = makeElement(id);
    return elements[id];
  };
  let readyHandler = null;
  const sandbox = {
    document: {
      getElementById: (id) => getElement(id),
      addEventListener: (evt, fn) => {
        if (evt === "DOMContentLoaded") readyHandler = fn;
      },
    },
    window: { location: { href: "http://localhost/results.html" } },
    fetch: fetchImpl,
    console,
  };
  vm.createContext(sandbox);
  vm.runInContext(ESCAPE_JS, sandbox, { filename: "escape.js" });
  vm.runInContext(RESULTS_JS, sandbox, { filename: "results.js" });
  return { sandbox, elements, getReady: () => readyHandler };
}

// Runs the page's real init() against fixture JSON keyed by absolute path
// (e.g. "/data/submissions.json") and returns the rendered elements.
async function render(fixtures) {
  const fetchImpl = async (url) => {
    if (!(url in fixtures)) throw new Error(`unexpected fetch: ${url}`);
    const entry = fixtures[url];
    if (entry instanceof Error) throw entry;
    return { ok: true, json: async () => entry };
  };
  const { elements, getReady } = createSandbox(fetchImpl);
  const ready = getReady();
  assert.ok(ready, "results.js must register a DOMContentLoaded handler");
  await ready();
  return elements;
}

const MALICIOUS_TITLE = '<script>alert(1)</script>';
const MALICIOUS_TEAM = '"><img src=x onerror=alert(2)>';
const MALICIOUS_REASONING = '<img src=x onerror=alert(3)>caveat & "quoted"';

function baseSubmissions() {
  return [
    {
      id: "sub_001",
      anon_id: "P-01",
      project_title: MALICIOUS_TITLE,
      team_name: MALICIOUS_TEAM,
    },
    { id: "sub_002", anon_id: "P-02", project_title: "Canopy Count", team_name: "Tree Folks" },
    { id: "sub_003", anon_id: "P-03", project_title: "Fair Assess", team_name: "Parcel People" },
    { id: "sub_004", anon_id: "P-04", project_title: "Bike Gaps", team_name: "Bike Brigade" },
  ];
}

test("comparison table escapes hostile project titles and team-derived data", async () => {
  const elements = await render({
    "/data/submissions.json": baseSubmissions(),
    "/data/results/bracket.json": {
      model_generated: true,
      mode: "ranked_list",
      ranking: ["P-01"],
      champion: "P-01",
      rounds: [],
    },
    "/data/results/comparison.json": {
      crowd_ranking: ["sub_001", "sub_002"],
      crowd_counts: { sub_001: 5, sub_002: 3 },
      panel_ranking: ["sub_002", "sub_001"],
      panel_means: {},
      spearman: null,
      per_persona: { "civic-impact": null },
      n: 8,
      invalid_ballots: 0,
      indicative: false,
      caveat: MALICIOUS_REASONING,
    },
  });

  const sideHtml = elements["side-by-side"].innerHTML;
  const agreementHtml = elements["agreement"].innerHTML;

  assert.ok(!sideHtml.includes("<script>"), "raw <script> must never reach innerHTML");
  assert.ok(sideHtml.includes("&lt;script&gt;alert(1)&lt;/script&gt;"), "title must be escaped");
  assert.ok(!agreementHtml.includes("<img src=x"), "raw caveat markup must never reach innerHTML");
  assert.ok(
    agreementHtml.includes("&lt;img src=x onerror=alert(3)&gt;caveat &amp; &quot;quoted&quot;"),
    "caveat must be escaped"
  );
  assert.ok(!agreementHtml.includes("null"), 'null spearman must not print the word "null"');
  assert.ok(agreementHtml.includes("Not enough variation to measure agreement."));
});

test("Panel mean is paired with the Panel-chose project in each row, not the crowd's pick or the row index", async () => {
  const submissions = [
    { id: "sub_001", anon_id: "P-01", project_title: "Alpha Project", team_name: "Team A" },
    { id: "sub_002", anon_id: "P-02", project_title: "Beta Project", team_name: "Team B" },
    { id: "sub_003", anon_id: "P-03", project_title: "Gamma Project", team_name: "Team C" },
  ];
  const elements = await render({
    "/data/submissions.json": submissions,
    "/data/results/bracket.json": {
      model_generated: true,
      mode: "ranked_list",
      ranking: ["P-01", "P-02", "P-03"],
      champion: "P-01",
      rounds: [],
    },
    "/data/results/comparison.json": {
      // Crowd and panel disagree on every row, so pairing panel_means by the
      // crowd's id (or by row index) instead of by that row's own
      // "Panel chose" id produces a WRONG number, not a coincidentally right
      // one — an ordering-agrees fixture could not catch this bug.
      crowd_ranking: ["sub_001", "sub_002", "sub_003"],
      panel_ranking: ["sub_003", "sub_001", "sub_002"],
      crowd_counts: { sub_001: 9, sub_002: 6, sub_003: 3 },
      panel_means: { sub_001: 4.2, sub_002: 2.5, sub_003: 3.75 },
      spearman: -0.5,
      per_persona: {},
      n: 18,
      invalid_ballots: 0,
      indicative: true,
      caveat: "",
    },
  });

  const sideHtml = elements["side-by-side"].innerHTML;
  assert.ok(
    sideHtml.includes("<th>Panel mean</th>"),
    "side-by-side table needs a Panel mean column header"
  );

  const tbody = sideHtml.split("<tbody>")[1].split("</tbody>")[0];
  const rows = tbody.split("<tr>").slice(1).map((r) => "<tr>" + r);
  assert.equal(rows.length, 3);

  // Row 1: crowd picked Alpha (sub_001); this row's Panel-chose entry is
  // Gamma (sub_003, mean 3.75) — not Alpha's own mean (4.20).
  assert.ok(rows[0].includes("Alpha Project"));
  assert.ok(rows[0].includes("Gamma Project"));
  assert.ok(rows[0].includes("3.75"), "row 1's mean should be Gamma's (the row's own Panel-chose pick)");
  assert.ok(!rows[0].includes("4.20"), "row 1 must not show Alpha's mean (the crowd's pick, not the panel's)");

  // Row 2: crowd picked Beta (sub_002); this row's Panel-chose entry is
  // Alpha (sub_001, mean 4.20) — not Beta's own mean (2.50).
  assert.ok(rows[1].includes("Beta Project"));
  assert.ok(rows[1].includes("Alpha Project"));
  assert.ok(rows[1].includes("4.20"), "row 2's mean should be Alpha's (the row's own Panel-chose pick)");
  assert.ok(!rows[1].includes("2.50"), "row 2 must not show Beta's mean (the crowd's pick, not the panel's)");

  // Row 3: crowd picked Gamma (sub_003); this row's Panel-chose entry is
  // Beta (sub_002, mean 2.50) — not Gamma's own mean (3.75).
  assert.ok(rows[2].includes("Gamma Project"));
  assert.ok(rows[2].includes("Beta Project"));
  assert.ok(rows[2].includes("2.50"), "row 3's mean should be Beta's (the row's own Panel-chose pick)");
  assert.ok(!rows[2].includes("3.75"), "row 3 must not show Gamma's mean (the crowd's pick, not the panel's)");
});

test("bracket entrants escape hostile titles and team names, byes render as byes", async () => {
  const elements = await render({
    "/data/submissions.json": baseSubmissions(),
    "/data/results/bracket.json": {
      model_generated: true,
      mode: "bracket",
      ranking: ["P-01", "P-02", "P-03", "P-04"],
      seeds: { "P-01": 1, "P-02": 2, "P-03": 3, "P-04": 4 },
      champion: "P-01",
      rounds: [
        [
          { a: "P-01", b: null, winner: "P-01", bye: true },
          {
            a: "P-02",
            b: "P-03",
            winner: "P-02",
            bye: false,
            votes: [
              { persona: "civic-impact", winner: "P-02", swap_confirmed: true },
              { persona: "craft", winner: "P-03", swap_confirmed: false },
            ],
            reasoning: { "civic-impact": MALICIOUS_REASONING },
          },
        ],
      ],
    },
    "/data/results/comparison.json": {
      crowd_ranking: [],
      crowd_counts: {},
      panel_ranking: [],
      panel_means: {},
      spearman: null,
      per_persona: {},
      n: 0,
      invalid_ballots: 0,
      indicative: false,
      caveat: "",
    },
  });

  const glassHtml = elements.glass.innerHTML;

  // XSS: hostile title/team/reasoning text must be escaped everywhere in the bracket too.
  assert.ok(!glassHtml.includes("<script>"), "raw <script> must never reach the bracket");
  assert.ok(glassHtml.includes("&lt;script&gt;alert(1)&lt;/script&gt;"));
  assert.ok(glassHtml.includes("&quot;&gt;&lt;img src=x onerror=alert(2)&gt;"));
  assert.ok(!glassHtml.includes("onerror=alert(3)>c"), "raw reasoning markup must never reach innerHTML");
  assert.ok(glassHtml.includes("&lt;img src=x onerror=alert(3)&gt;caveat"));

  // Byes render as byes, not as a matchup against an empty opponent.
  const byeLi = glassHtml.split('<li class="matchup">')[1];
  assert.ok(byeLi.includes("pane--bye"), "bye matchup should use the bye pane style");
  assert.ok(byeLi.includes('matchup__note">Bye'), "bye matchup should be labelled Bye");
  assert.ok(!byeLi.includes("<button"), "a bye must not render as a clickable two-entrant matchup");

  // Contested matchup exposes each persona's vote, pick, and swap outcome.
  assert.ok(glassHtml.includes("civic impact"), "persona name should render (hyphens as spaces)");
  assert.ok(glassHtml.includes("Held after the position swap."));
  assert.ok(glassHtml.includes("Did not hold after the position swap."));
  assert.ok(glassHtml.includes('aria-controls="details-r1-m2"'));
  assert.ok(glassHtml.includes('id="details-r1-m2"'));
  assert.ok(glassHtml.includes("hidden"), "expandable detail panels start hidden");

  // Champion pane uses --glass exactly on the champion, never elsewhere in the CSS
  // (bracket.css owns that rule); here we just confirm the champion markup exists once.
  assert.equal((glassHtml.match(/pane--champion/g) || []).length, 1);
});

test("ranked_list mode renders the ordered list and the fewer-than-four note", async () => {
  const elements = await render({
    "/data/submissions.json": [
      { id: "sub_001", anon_id: "P-01", project_title: "Solo Entry", team_name: "Only Team" },
      { id: "sub_002", anon_id: "P-02", project_title: "Second Entry", team_name: "Other Team" },
    ],
    "/data/results/bracket.json": {
      model_generated: true,
      mode: "ranked_list",
      ranking: ["P-01", "P-02"],
      champion: "P-01",
      rounds: [],
    },
    "/data/results/comparison.json": {
      crowd_ranking: ["sub_001", "sub_002"],
      crowd_counts: { sub_001: 2, sub_002: 1 },
      panel_ranking: ["sub_001", "sub_002"],
      panel_means: {},
      spearman: null,
      per_persona: {},
      n: 3,
      invalid_ballots: 0,
      indicative: false,
      caveat: "",
    },
  });

  const glassHtml = elements.glass.innerHTML;
  assert.ok(
    glassHtml.includes(
      "Fewer than four projects were entered, so the panel published a ranking rather than a bracket."
    )
  );
  assert.ok(glassHtml.includes('<ol class="ranked-list">'));
  assert.ok(glassHtml.includes("Solo Entry"));
  assert.ok(glassHtml.includes("Second Entry"));
  assert.ok(!glassHtml.includes('class="rounds"'), "ranked_list mode must not render the bracket glass");
  assert.ok(!glassHtml.includes("round--champion"));
});

test("a fetch failure renders a friendly fallback instead of throwing", async () => {
  const elements = await render({
    "/data/submissions.json": [],
    "/data/results/bracket.json": new Error("network down"),
    "/data/results/comparison.json": {},
  });

  assert.ok(elements.agreement.innerHTML.includes("Results are not available yet."));
  assert.ok(elements.glass.innerHTML.includes("Results are not available yet."));
});

test("toggleDetails flips aria-expanded and hidden in both directions", () => {
  const { sandbox } = createSandbox(async () => ({ ok: true, json: async () => ({}) }));
  const button = { _attrs: {}, getAttribute(n) { return this._attrs[n] ?? "false"; }, setAttribute(n, v) { this._attrs[n] = String(v); } };
  const details = { hidden: true };

  sandbox.toggleDetails(button, details);
  assert.equal(button.getAttribute("aria-expanded"), "true");
  assert.equal(details.hidden, false);

  sandbox.toggleDetails(button, details);
  assert.equal(button.getAttribute("aria-expanded"), "false");
  assert.equal(details.hidden, true);
});

// Optional smoke test against the real mock-panel output. site/data/ is a
// gitignored build artifact (see task-15-brief.md Step 4), so this only runs
// when a developer has already generated it locally; it is skipped otherwise
// rather than failing a fresh checkout or CI.
test("smoke test against locally generated mock panel output, if present", async (t) => {
  const dataDir = path.join(ROOT, "site", "data");
  const required = [
    path.join(dataDir, "submissions.json"),
    path.join(dataDir, "results", "bracket.json"),
    path.join(dataDir, "results", "comparison.json"),
  ];
  if (!required.every((p) => fs.existsSync(p))) {
    t.skip("site/data/ not generated locally — run judging.run_panel --mock first");
    return;
  }

  const [submissions, bracket, comparison] = required.map((p) =>
    JSON.parse(fs.readFileSync(p, "utf-8"))
  );
  const elements = await render({
    "/data/submissions.json": submissions,
    "/data/results/bracket.json": bracket,
    "/data/results/comparison.json": comparison,
  });

  for (const el of Object.values(elements)) {
    assert.ok(!/\bnull\b/.test(el.innerHTML), `no literal "null" in ${el.id}: ${el.innerHTML.slice(0, 200)}`);
    assert.ok(!/\bNaN\b/.test(el.innerHTML), `no literal "NaN" in ${el.id}`);
  }
  assert.ok(elements.glass.innerHTML.length > 0);
  assert.ok(elements["side-by-side"].innerHTML.length > 0);
});

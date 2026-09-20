// tests/js/results.ties.test.js
//
// C1: spec §6.3 says tied projects "share a rank and are displayed as tied",
// and that a tie on a gift-card boundary is flagged for CISC. results.js used
// to render the row index + 1 as a hard ordinal, so two projects on identical
// vote counts were published as 3rd and 4th — an ordering that came from
// submission id, i.e. from who filed first.
//
// Run with: node --test tests/js/*.test.js

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
    querySelectorAll() {
      return [];
    },
  };
}

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
  return { elements, getReady: () => readyHandler };
}

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

const SUBMISSIONS = [
  { id: "sub_001", anon_id: "P-01", project_title: "Alpha", team_name: "A" },
  { id: "sub_002", anon_id: "P-02", project_title: "Beta", team_name: "B" },
  { id: "sub_003", anon_id: "P-03", project_title: "Gamma", team_name: "C" },
  { id: "sub_004", anon_id: "P-04", project_title: "Delta", team_name: "D" },
];

const EMPTY_BRACKET = {
  model_generated: true,
  mode: "ranked_list",
  ranking: ["P-01"],
  champion: "P-01",
  rounds: [],
};

// Gamma and Delta tie for third on identical counts, with three gift cards:
// the tie lands exactly on the award boundary.
function tiedComparison(overrides) {
  return Object.assign(
    {
      crowd_ranking: ["sub_001", "sub_002", "sub_003", "sub_004"],
      crowd_ranks: { sub_001: 1, sub_002: 2, sub_003: 3, sub_004: 3 },
      crowd_ties: [["sub_003", "sub_004"]],
      award_count: 3,
      award_boundary_tie: true,
      award_boundary_tie_ids: ["sub_003", "sub_004"],
      crowd_counts: { sub_001: 9, sub_002: 7, sub_003: 5, sub_004: 5 },
      panel_ranking: [],
      panel_means: {},
      spearman: null,
      per_persona: {},
      n: 14,
      invalid_ballots: 0,
      indicative: false,
      caveat: "",
    },
    overrides || {}
  );
}

function rowsOf(html) {
  const tbody = html.split("<tbody>")[1].split("</tbody>")[0];
  return tbody.split("<tr>").slice(1).map((r) => "<tr>" + r);
}

function rankCellOf(row) {
  const cell = row.match(/<td class="rank"[^>]*>([\s\S]*?)<\/td>/);
  assert.ok(cell, `row has no rank cell: ${row}`);
  return cell[1];
}

test("tied projects share a rank instead of being numbered 3 and 4", async () => {
  const elements = await render({
    "/data/submissions.json": SUBMISSIONS,
    "/data/results/bracket.json": EMPTY_BRACKET,
    "/data/results/comparison.json": tiedComparison(),
  });

  const rows = rowsOf(elements["side-by-side"].innerHTML);
  assert.equal(rows.length, 4);

  const ranks = rows.map((row) => rankCellOf(row).replace(/<[^>]*>/g, "").trim());
  assert.match(ranks[0], /^1\b/);
  assert.match(ranks[1], /^2\b/);
  // The two tied rows both read 3. Neither may read 4.
  assert.match(ranks[2], /^3\b/, "first tied row must share rank 3");
  assert.match(ranks[3], /^3\b/, "second tied row must share rank 3, not be numbered 4");
  assert.ok(
    !ranks.some((r) => /^4\b/.test(r)),
    `no row may claim 4th place when two projects share 3rd: ${JSON.stringify(ranks)}`
  );
});

test("tied rows are marked as tied, not silently equal-numbered", async () => {
  const elements = await render({
    "/data/submissions.json": SUBMISSIONS,
    "/data/results/bracket.json": EMPTY_BRACKET,
    "/data/results/comparison.json": tiedComparison(),
  });

  const rows = rowsOf(elements["side-by-side"].innerHTML);
  assert.match(rankCellOf(rows[2]), /tied/i, "a shared rank must say so");
  assert.match(rankCellOf(rows[3]), /tied/i);
  assert.ok(!/tied/i.test(rankCellOf(rows[0])), "an untied row must not claim a tie");
});

test("a tie on the gift-card boundary is surfaced for CISC", async () => {
  const elements = await render({
    "/data/submissions.json": SUBMISSIONS,
    "/data/results/bracket.json": EMPTY_BRACKET,
    "/data/results/comparison.json": tiedComparison(),
  });

  const html = elements["agreement"].innerHTML;
  assert.match(html, /CISC/, "the boundary tie must name who decides it");
  assert.ok(html.includes("Gamma") && html.includes("Delta"), "name the tied projects");
});

test("no boundary notice when nothing is tied across the award line", async () => {
  const elements = await render({
    "/data/submissions.json": SUBMISSIONS,
    "/data/results/bracket.json": EMPTY_BRACKET,
    "/data/results/comparison.json": tiedComparison({
      crowd_ranks: { sub_001: 1, sub_002: 2, sub_003: 3, sub_004: 4 },
      crowd_ties: [],
      award_boundary_tie: false,
      award_boundary_tie_ids: [],
      crowd_counts: { sub_001: 9, sub_002: 7, sub_003: 5, sub_004: 2 },
    }),
  });
  assert.ok(!/CISC/.test(elements["agreement"].innerHTML));
});

test("a hostile project title in a boundary-tie notice is escaped", async () => {
  const hostile = [
    { id: "sub_001", anon_id: "P-01", project_title: "Alpha", team_name: "A" },
    { id: "sub_002", anon_id: "P-02", project_title: "Beta", team_name: "B" },
    { id: "sub_003", anon_id: "P-03", project_title: "<script>alert(1)</script>", team_name: "C" },
    { id: "sub_004", anon_id: "P-04", project_title: "Delta", team_name: "D" },
  ];
  const elements = await render({
    "/data/submissions.json": hostile,
    "/data/results/bracket.json": EMPTY_BRACKET,
    "/data/results/comparison.json": tiedComparison(),
  });
  const html = elements["agreement"].innerHTML;
  assert.ok(!html.includes("<script>"), "raw <script> must never reach innerHTML");
  assert.ok(html.includes("&lt;script&gt;alert(1)&lt;/script&gt;"));
});

test("a comparison without rank data still renders sequential fallback ordinals", async () => {
  // Older comparison.json files (written before C1) carry no crowd_ranks.
  const legacy = tiedComparison();
  delete legacy.crowd_ranks;
  delete legacy.crowd_ties;
  delete legacy.award_boundary_tie;
  delete legacy.award_boundary_tie_ids;

  const elements = await render({
    "/data/submissions.json": SUBMISSIONS,
    "/data/results/bracket.json": EMPTY_BRACKET,
    "/data/results/comparison.json": legacy,
  });
  const rows = rowsOf(elements["side-by-side"].innerHTML);
  assert.match(rankCellOf(rows[0]).trim(), /^1\b/);
  assert.match(rankCellOf(rows[3]).trim(), /^4\b/);
});

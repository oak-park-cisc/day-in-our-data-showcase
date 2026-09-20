// tests/js/results.abstained.test.js
//
// I3: a submission the panel did not fully score is excluded from the
// bracket, the ranking and every statistic. Spec §8 requires that exclusion
// be "shown in the UI. Never silent."
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
    return { ok: true, json: async () => fixtures[url] };
  };
  const { elements, getReady } = createSandbox(fetchImpl);
  const ready = getReady();
  assert.ok(ready, "results.js must register a DOMContentLoaded handler");
  await ready();
  return elements;
}

const EMPTY_BRACKET = {
  model_generated: true,
  mode: "ranked_list",
  ranking: ["P-01"],
  champion: "P-01",
  rounds: [],
};

function comparison(overrides) {
  return Object.assign(
    {
      crowd_ranking: ["sub_001", "sub_002", "sub_003"],
      crowd_ranks: { sub_001: 1, sub_002: 2, sub_003: 3 },
      crowd_ties: [],
      award_count: 3,
      award_boundary_tie: false,
      award_boundary_tie_ids: [],
      crowd_counts: { sub_001: 9, sub_002: 6, sub_003: 3 },
      panel_ranking: ["sub_001", "sub_002"],
      panel_means: { sub_001: 4.0, sub_002: 2.0 },
      panel_abstained: ["sub_003"],
      spearman: 1,
      spearman_basis: "bracket finish",
      per_persona: {},
      n: 14,
      invalid_ballots: 0,
      indicative: false,
      caveat: "",
    },
    overrides || {}
  );
}

const SUBMISSIONS = [
  { id: "sub_001", anon_id: "P-01", project_title: "Alpha", team_name: "A" },
  { id: "sub_002", anon_id: "P-02", project_title: "Beta", team_name: "B" },
  { id: "sub_003", anon_id: "P-03", project_title: "Gamma", team_name: "C" },
];

test("a submission the panel did not fully score is named on the page", async () => {
  const elements = await render({
    "/data/submissions.json": SUBMISSIONS,
    "/data/results/bracket.json": EMPTY_BRACKET,
    "/data/results/comparison.json": comparison(),
  });
  const html = elements["agreement"].innerHTML;
  assert.match(html, /abstain/i, "the exclusion must be labelled, not silent");
  assert.ok(html.includes("Gamma"), "the excluded project must be named");
});

test("nothing is said when the panel scored every submission", async () => {
  const elements = await render({
    "/data/submissions.json": SUBMISSIONS,
    "/data/results/bracket.json": EMPTY_BRACKET,
    "/data/results/comparison.json": comparison({ panel_abstained: [] }),
  });
  assert.ok(!/abstain/i.test(elements["agreement"].innerHTML));
});

test("a hostile title in the abstention notice is escaped", async () => {
  const hostile = SUBMISSIONS.slice(0, 2).concat([
    {
      id: "sub_003",
      anon_id: "P-03",
      project_title: '"><img src=x onerror=alert(1)>',
      team_name: "C",
    },
  ]);
  const elements = await render({
    "/data/submissions.json": hostile,
    "/data/results/bracket.json": EMPTY_BRACKET,
    "/data/results/comparison.json": comparison(),
  });
  const html = elements["agreement"].innerHTML;
  assert.ok(!html.includes("<img src=x"), "raw markup must never reach innerHTML");
  assert.ok(html.includes("&lt;img src=x onerror=alert(1)&gt;"));
});

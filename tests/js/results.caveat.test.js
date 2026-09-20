// tests/js/results.caveat.test.js
//
// I4: results.js used to render only comparison.caveat and never read
// comparison.indicative, so a below-floor result whose caveat had been
// overwritten (or simply left empty) published with no §6.4 disclosure at
// all. The page must derive the disclosure from `indicative` itself, so it
// cannot be silenced by whatever happens to be in a text field.
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

const SUBMISSIONS = [
  { id: "sub_001", anon_id: "P-01", project_title: "Alpha", team_name: "A" },
  { id: "sub_002", anon_id: "P-02", project_title: "Beta", team_name: "B" },
];

const EMPTY_BRACKET = { model_generated: true, mode: "bracket", rounds: [], champion: null };

function comparison(overrides) {
  return Object.assign(
    {
      crowd_ranking: ["sub_001", "sub_002"],
      crowd_ranks: { sub_001: 1, sub_002: 2 },
      crowd_ties: [],
      award_count: 3,
      award_boundary_tie: false,
      award_boundary_tie_ids: [],
      crowd_counts: { sub_001: 6, sub_002: 3 },
      panel_ranking: [],
      panel_means: {},
      panel_abstained: [],
      spearman: null,
      per_persona: {},
      n: 9,
      invalid_ballots: 0,
      indicative: true,
      caveat: "",
      notes: [],
      panel_published: false,
    },
    overrides || {}
  );
}

async function agreementHtml(overrides) {
  const elements = await render({
    "/data/submissions.json": SUBMISSIONS,
    "/data/results/bracket.json": EMPTY_BRACKET,
    "/data/results/comparison.json": comparison(overrides),
  });
  return elements["agreement"].innerHTML;
}

test("an indicative result with an empty caveat still discloses the turnout floor", async () => {
  const html = await agreementHtml({ caveat: "" });
  assert.match(html, /indicative only/i, "the §6.4 disclosure must not depend on caveat text");
});

test("the sample size is stated on the page for an indicative result", async () => {
  const html = await agreementHtml({ caveat: "" });
  assert.match(html, /\b9\b/, "§6.4 requires the sample size be stated");
});

test("the supplied caveat is preferred when one is present", async () => {
  const html = await agreementHtml({
    caveat: "Fewer than 10 valid ballots were cast. Indicative only, as the spec puts it.",
  });
  assert.match(html, /as the spec puts it/);
  // …and not doubled up with the built-in fallback.
  assert.equal((html.match(/Fewer than 10 valid ballots/g) || []).length, 1);
});

test("notes render alongside the caveat rather than replacing it", async () => {
  const html = await agreementHtml({
    caveat: "Fewer than 10 valid ballots were cast. Indicative only.",
    notes: ["AI panel results are not published yet."],
  });
  assert.match(html, /Indicative only/);
  assert.match(html, /AI panel results are not published yet/);
});

test("a healthy turnout with no notes says nothing extra", async () => {
  const html = await agreementHtml({ indicative: false, caveat: "", n: 42, notes: [] });
  assert.ok(!/indicative/i.test(html));
});

test("note text is escaped", async () => {
  const html = await agreementHtml({
    indicative: false,
    caveat: "",
    notes: ['<img src=x onerror=alert(1)>'],
  });
  assert.ok(!html.includes("<img src=x"));
  assert.ok(html.includes("&lt;img src=x onerror=alert(1)&gt;"));
});

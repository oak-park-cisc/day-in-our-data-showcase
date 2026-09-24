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

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

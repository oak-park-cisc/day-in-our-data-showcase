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

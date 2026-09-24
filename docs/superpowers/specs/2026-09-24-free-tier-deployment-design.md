# Free-Tier Deployment — Public Repo, Live Data, Ballots Out of the Repo

**Date:** 2026-09-24
**Status:** Draft for owner review
**Event:** Saturday, October 3, 2026 (nine days out)
**Amends:** `2026-09-19-day-in-our-data-showcase-design.md` §3 (architecture), §3.1 (data flow), §4.4 (ballot), §6.3 (tally). Supersedes decision-log #33.

---

## 1. Why this exists

Connecting the site to Netlify hit a paywall. Netlify's free plan does not
continuously deploy from a **private, organization-owned** GitHub repository;
that needs Pro at $20/month ([Netlify, 2022](https://answers.netlify.com/t/update-connecting-private-organization-owned-github-repositories/72151)).
`oak-park-cisc/day-in-our-data-showcase` was exactly that.

The owner made the repo **public on 2026-09-24**, after a history scan found no
secrets, no ballot codes, and no personal data beyond the commit author email
already public on her other repos. Public repos connect to Netlify's free plan.

That exposed two further problems, which this spec fixes:

1. **The deploy budget.** Netlify's free plan is 300 credits/month, 15 credits
   per production deploy — about 20 deploys — and a hard cap: at 300 the site
   pauses until next month ([Netlify docs](https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/credit-based-pricing-plans/)).
   Today every sync, judge, and tally commit rebuilds the site, and sync alone
   can commit every 15 minutes for six hours on event day. The site could go
   dark mid-vote.
2. **Ballot secrecy.** `sync-submissions.yml` commits `data/ballots.json`
   (`{code_hash, picks, cast_at}` per ballot). In a public repo, anyone holding
   a slip code hashes it and reads that person's picks. Decision #33 accepted
   this on the premise that codes stay on the slips; making the repo public
   removes the last reason to accept it.

Form submissions are free on every credit plan as of 2026-04-14
([changelog](https://www.netlify.com/changelog/2026-04-14-pricing-updates-april-2026/)),
so Netlify Forms costs nothing.

## 2. Decisions

| # | Decision | Reason |
|---|---|---|
| D1 | Stay on Netlify, free plan, Git-connected to the public repo | Netlify Forms carries submissions, file uploads, and ballots with no backend of ours. Replacing it nine days out means new vote-handling code on a deadline. Moving off Netlify is a post-event project, if ever. |
| D2 | Pages read `data/` live from `raw.githubusercontent.com` | Data changes stop needing a deploy. Updates show within ~5 minutes (GitHub's raw CDN cache). |
| D3 | Pages fall back to the same-origin `/data/` snapshot if the raw fetch fails | GitHub rate-limits unauthenticated raw requests at ~5,000/hour per IP ([GitHub](https://github.com/orgs/community/discussions/160828), [changelog](https://github.blog/changelog/2025-05-08-updated-rate-limits-for-unauthenticated-requests/)). A library's wifi puts every attendee behind one IP. Expected load is well under the limit, but the fallback turns a 429 into slightly stale data instead of an empty page. |
| D4 | Every bot data commit carries `[skip netlify]` | Netlify's documented commit-message skip. Deterministic, no first-build edge cases, and a human commit touching `site/` still deploys normally. |
| D5 | Ballots never enter the repo | `tally.yml` reads ballots from the Netlify Forms API in memory and commits only aggregates. Closes the attribution risk at the source instead of arguing about it. |
| D6 | Custom domain = one new CNAME, DNS-only | See §7. No existing DNS record, Worker, Access app, or setting on the owner's Cloudflare account is touched. |

### 2.1 Out of scope

- Moving off Netlify (Cloudflare Pages + D1/R2, or GitHub Pages + an external
  form service). Revisit after the event.
- Branch protection on `main`. Now available because the repo is public; worth
  doing, but independent of this work. Listed in the runbook as optional.
- Any change to `voting/tally.py`, `voting/ranking.py`, `voting/compare.py`, or
  judging. Ballot validation, first-valid-ballot-wins, ties, the turnout floor,
  and the one-winner rule are unchanged.

## 3. Architecture after this change

```
                         ┌─────────────── Netlify (free) ───────────────┐
 participant ─ form ───▶ │ Forms: submission, ballot                    │
                         │ Static site: site/ (+ /data snapshot)        │◀─ deploys only on
                         └───────────────▲──────────────────────────────┘   non-[skip netlify] commits
                                         │ Forms API (NETLIFY_TOKEN)
            ┌────────────────────────────┴───────────────┐
            │ GitHub Actions                             │
            │  sync-submissions.yml → data/submissions.json, id_map.json   [skip netlify]
            │  judge.yml            → data/results/{bracket,scores}.json   [skip netlify]
            │  tally.yml  ── ballots in memory only ──▶ data/results/{vote,comparison}.json [skip netlify]
            └────────────────────────────┬───────────────┘
                                         │ git push (public repo)
 browser ── fetch data/*.json ──▶ raw.githubusercontent.com/oak-park-cisc/day-in-our-data-showcase/main/data/…
            └── on failure ─────▶ same-origin /data/… (snapshot from the last deploy)
```

## 4. Components

### 4.1 `site/scripts/data.js` — new

One job: turn a data path into a fetched JSON value, live-first.

- `DATA_LIVE_BASE = "https://raw.githubusercontent.com/oak-park-cisc/day-in-our-data-showcase/main/data/"`
- `DATA_SNAPSHOT_BASE = "/data/"`
- `fetchData(relPath)` — e.g. `fetchData("results/comparison.json")`. Tries the
  live URL with `{ cache: "no-store" }`; on a network error or non-2xx, tries
  the snapshot URL; if both fail, throws, so each page's existing
  "not available yet" handling runs unchanged.
- Rejects `relPath` values that are absolute, contain `..`, or start with `/` —
  the bases are fixed and callers pass literals, so this is a tripwire, not a
  feature.

Loaded before each page script, alongside `escape.js`, in `index.html`,
`vote.html`, `results.html`.

### 4.2 Page scripts — changed

`gallery.js`, `vote.js`, `results.js` replace their four `fetch("/data/…")` /
`loadJSON("/data/…")` calls with `fetchData(…)`. No rendering change.

### 4.3 `netlify.toml` — changed

Build command becomes `mkdir -p data && rm -rf site/data && cp -r data site/data`.

- The copy stays: it is the D3 fallback snapshot.
- `rm -f site/data/ballots.json` is removed, because `data/ballots.json` no
  longer exists. Instead, a test (§6) asserts no file under `data/` holds
  ballot-level fields, and `.gitignore` gains `data/ballots.json` as a second
  guard against a stray local run being committed.
- The long ballot-secrecy comment is replaced by a short one pointing here.

### 4.4 `scripts/sync_netlify.py` — changed

- `sync()` stops fetching the ballot form and stops writing `ballots.json`. It
  writes `submissions.json` and `id_map.json` only.
- New public `fetch_ballots(token, site_id=None, get_json=_http_get_json) -> list[dict]`:
  resolves the `ballot` form, pages every submission with the existing
  `fetch_all_submissions`, and returns `build_ballots(...)`. It keeps the
  existing rule that ballot-form fetches never put a response body in an error
  (that body can hold raw voter codes).
- `map_ballot` still hashes the code, so `tally()` receives the same shape it
  always has and `tally.yml`'s `hash_code` comparison is unchanged.
- `_hash_code`'s docstring is cut to what is still true: the hash lets the tally
  compare against `BALLOT_CODES` without handling plaintext codes beyond the
  fetch; ballots are held in memory and never written. The code-recovery and
  attribution analysis goes, because there is no longer a published file to
  analyse.

### 4.5 `.github/workflows/sync-submissions.yml` — changed

- Step renamed "Sync submissions from Netlify Forms".
- `git add data/submissions.json data/id_map.json` (no ballots).
- Commit message `chore: sync submissions from Netlify [skip netlify]`.

### 4.6 `.github/workflows/tally.yml` — changed

- The tally step gains `NETLIFY_TOKEN` and `NETLIFY_SITE_ID` in its `env:`.
- Replaces the `data/ballots.json` read with `fetch_ballots(os.environ["NETLIFY_TOKEN"], os.environ.get("NETLIFY_SITE_ID") or None)`.
- The missing-file guard checks only `data/submissions.json`.
- A `NetlifySyncError` exits 1 with one line naming the problem, never a
  response body.
- Commits only `data/results` — `vote.json` (counts, ranks, valid/invalid
  totals) and `comparison.json`. Neither contains codes, hashes, or per-ballot
  rows; this is already true and a test pins it (§6).
- Commit message `chore: publish participant vote tally [skip netlify]`.

### 4.7 `.github/workflows/judge.yml` — changed

Commit message `chore: publish AI panel results [skip netlify]`. Nothing else.

## 5. Error handling

| Failure | Behaviour |
|---|---|
| raw.githubusercontent.com 429 / down / offline | `fetchData` falls back to the snapshot. Page renders last-deployed data. |
| Both live and snapshot fail | Existing per-page "not available yet" message. |
| Tally can't reach Netlify, or token lacks access | `tally.yml` fails with a one-line error; nothing committed. Re-run after fixing the secret. |
| Ballot form has zero submissions | `fetch_ballots` returns `[]`; tally publishes zero counts and the indicative caveat, as today. |
| Deploy budget | Expected deploys from now through the event: 1 first deploy, ~2–5 for code fixes, 1 manual post-tally snapshot deploy — under 10 of the ~20. Adding a custom domain needs no deploy. Bot commits deploy zero times. |

The snapshot goes stale between deploys by design. On event day it is a
fallback, not the source of truth; the runbook says to trigger one manual
deploy after the tally so the snapshot matches the published result.

## 6. Testing

Tests first for each change; each new test is observed failing before its fix,
per this project's standing practice.

**Python**
- `test_sync_netlify.py`: `sync()` writes no `ballots.json` and never requests
  the ballot form's submissions; `fetch_ballots()` resolves the ballot form,
  pages, hashes codes, and never includes a response body in its errors.
- `test_netlify_config.py` rewritten: executes the build command against a
  seeded tree and asserts `site/data/` mirrors `data/`; asserts no JSON under
  `data/` in the real repo contains `code`, `code_hash`, or `picks` keys.
- `test_sync_submissions_workflow.py` / `test_tally_workflow.py`: the sync
  step's `git add` names no ballots file; the tally step declares
  `NETLIFY_TOKEN` and `NETLIFY_SITE_ID`; no workflow reads `data/ballots.json`.
- New `test_skip_netlify.py`: every `git commit -m` in every workflow under
  `.github/workflows/` contains `[skip netlify]`.

**JavaScript** (`node --test tests/js/*.test.js`, existing vm harness)
- New `data.test.js`: live success returns live data without touching the
  snapshot; live 429 → snapshot; live network error → snapshot; both fail →
  throws; `..`/absolute paths rejected.
- Existing results tests load `data.js` before `results.js` and keep passing
  with the fake fetch keyed by the new live URLs.

**Manual, once live** (runbook)
- First deploy succeeds; a test submission appears in the gallery within ~5
  minutes of a sync, with no new Netlify deploy in the deploy list.
- The three unconfirmed Netlify API shapes from the existing runbook
  (`created_at`, artifact field, pagination) — unchanged.

## 7. Custom domain

The owner's DNS is on Cloudflare, on an account that also runs family sites.
Standing rule: nothing already on that account may be modified. This design
adds exactly one object.

1. Netlify → Domain management → add `<subdomain>.<domain>` (owner picks the
   name at deploy time).
2. Cloudflare → DNS → **add** one `CNAME <subdomain> → <site>.netlify.app`,
   proxy status **DNS only** (grey cloud). Proxying through Cloudflare breaks
   Netlify's certificate provisioning and is unnecessary.
3. Netlify provisions the Let's Encrypt certificate itself.

**Risk and how it is contained:**
- Nothing existing changes; no apex, wildcard, or `www` record is touched.
- The site gets no access to the owner's account or other sites. A CNAME is
  a pointer, nothing more.
- **Dangling-record takeover** is the one real risk: if the Netlify site is
  deleted while the CNAME remains, someone else could claim that hostname on
  Netlify and serve content under the owner's domain. Mitigation: the runbook's
  teardown step deletes the CNAME **before** deleting the Netlify site.

## 8. Documentation changes

- `docs/deployment-runbook.md` rewritten for: connecting the public repo on the
  free plan, the deploy budget and `[skip netlify]`, the tally's new
  `NETLIFY_TOKEN` need, the custom domain (§7), post-tally manual deploy, and
  teardown order. Optional: enable branch protection on `main`.
- `docs/decision-log.md` gains **#35** (ballots out of the repo; supersedes #33)
  and **#36** (free-tier Netlify with live data and `[skip netlify]`).
- Original spec gains a dated amendment note pointing here, leaving the
  original text intact, as was done for §1.2.

## 9. Risks

| Risk | Mitigation |
|---|---|
| `[skip netlify]` silently stops being honoured | Watch the Netlify deploy list during the first sync dry run; the runbook names this check. |
| raw CDN caching delays a result reveal by up to ~5 minutes | Acceptable; the runbook says so. |
| Tally now depends on Netlify being up at tally time | Tally runs after the event, on demand, and can simply be re-run. |
| Ballots are no longer auditable from the repo | They stay in Netlify's dashboard (Forms → ballot), visible only to the account holders. That is the right audit location. |

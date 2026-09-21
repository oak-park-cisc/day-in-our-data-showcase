# Deployment runbook

Everything needed to take this repository from merged code to a live site that
accepts submissions and ballots. Written for the repo owner; no prior context
assumed.

The code is complete and merged. What remains needs a Netlify account and
GitHub repository secrets, which is why it was left undone during the build.

---

## 1. Connect the Netlify site

1. Netlify → **Add new site** → **Import an existing project** → select
   `oak-park-cisc/day-in-our-data-showcase`, branch **`main`**.
2. Confirm the build settings Netlify auto-detects match `netlify.toml`:
   - publish directory: `site`
   - build command: `mkdir -p data && rm -rf site/data && cp -r data site/data && rm -f site/data/ballots.json`
3. Site settings → **Forms** → confirm form detection is enabled. Netlify
   auto-detects the `submission` and `ballot` forms from `site/index.html` and
   `site/vote.html` on the first successful deploy.
4. Deploy once. Then submit one real test entry through the submission form and
   confirm it appears under Site → Forms → submission.

## 2. Generate the ballot codes — offline

```
python -m voting.generate_codes --count <N>
```

Run this on a machine that will not commit its output. It prints two things:
the sheet of slips to cut up for check-in, and the comma-joined string for the
`BALLOT_CODES` secret.

**Never paste the codes into a file in this repository.** It is public, and a
committed code lets anyone vote as that attendee.

## 3. Add the repository secrets

GitHub repo → Settings → Secrets and variables → Actions.

| Secret | Required | What it is |
|---|---|---|
| `NETLIFY_TOKEN` | yes | Netlify personal access token (User settings → Applications → New access token) with access to this site |
| `ANTHROPIC_API_KEY` | yes | Only used by `judge.yml` on a real (non-mock) run |
| `BALLOT_CODES` | yes | The comma-joined string from step 2 |
| `NETLIFY_SITE_ID` | only if needed | Set this only if the sync fails with "Multiple Netlify forms named ... found" — it scopes the lookup when your token can see same-named forms on several sites |

## 4. Verify the pipeline before the event

**Sync.** Actions → `sync-submissions.yml` → Run workflow. Confirm it reaches
the Netlify Forms API and commits `data/submissions.json`, `data/ballots.json`
and `data/id_map.json`. The first run may be an empty diff if nobody has
submitted — that is expected.

**Judging dry run.** Actions → "Run AI judging panel" → Run workflow, leaving
`mock` at its default `true`. This exercises the whole pipeline — commits
`data/results/bracket.json`, triggers a Netlify rebuild, renders `results.html`
— at **zero API spend**. Do this before the event; it is the cheap way to find
out the wiring works.

**Tally.** Actions → `tally.yml` → Run workflow. It requires
`data/submissions.json` and `data/ballots.json` to exist already, and exits with
a clear message naming the missing file if not.

## 5. During and after the event

`sync-submissions.yml` runs automatically every 15 minutes during Saturday
16:00–21:59 UTC (11:00 a.m.–4:59 p.m. Central). It also runs on demand.

After submissions close, run `judge.yml` with **`mock` unticked** for the real
panel — this is the only step that spends money, roughly $2 at
`claude-sonnet-5` for a 20-project event — then run `tally.yml` to publish the
vote and the comparison.

---

## Checks that could not be made without a live site

These are fake-tested only. One real `sync-submissions.yml` dispatch against the
live Netlify site clears all three at once, and all three can silently produce a
wrong result:

- **`created_at`** is assumed to be the Netlify submission timestamp field, and
  is used to order first-time id assignment. Confirm it exists on a real
  submission.
- **The artifact upload field shape** — the sync script tolerates both a plain
  URL string and a `{url, filename, size}` object, because Netlify's public
  documentation does not pin it down. Confirm which you actually get.
- **Pagination** — `fetch_all_submissions` pages until a short page returns.
  Confirm against a form with real submissions.

`results.html` also gained five CSS classes (tied-rank chips, the award-boundary
notice, the panel-abstained notice) after the last visual pass, so they have
never been seen rendered. Worth a browser look, particularly the tied-row
density: on a low-turnout run most projects tie at zero votes, so many rows will
carry a "tied" chip at once. That is correct behaviour, but it should be checked
that it reads well.

## Two things to know before you run this for real

**Never delete a Netlify form submission after the showcase publishes.** Public
ids are held stable across syncs by `data/id_map.json`, so deleting one no
longer renumbers the others — but do not rely on that if the map is ever lost or
bypassed. Ballots record their picks by public id.

**There are no gift cards.** The prizes changed (spec §1.2, amended
2026-09-21): every participant gets a participation keychain, not rank-based,
and one project wins the vote. The award cut is
`voting.ranking.DEFAULT_AWARD_COUNT`, now `1`, kept as an overridable constant
rather than a hardcoded literal. It decides where a tie counts as landing on
the award boundary; at `1` that is a tie for first place, which the page
publishes as a shared win rather than escalating it to anyone.

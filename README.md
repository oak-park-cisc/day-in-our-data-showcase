# Day in Our Data — Showcase

Companion site for [Day in Our Data](https://github.com/oak-park-cisc/Oak_Park_Day_in_our_Data), the Village of Oak Park civic hackathon run by the Civic Information Systems Commission.

**Event:** Saturday, October 3, 2026, 11 a.m. to 3 p.m., Dole Branch Library, 255 Augusta St., Oak Park, IL

## What this is

Three things the event program asks for and one experiment:

1. **Submission intake** — the one place every team enters: what they built, what it solves for, how they got from the raw data to the result, and a zip upload (Track A, the Civic Spark workspace) or a repository link (Track B, their own tools).
2. **Public showcase** — everything every team produced, in one place.
3. **Participant vote** — attendees pick their top three, one ballot per device. **The vote decides the awards**, exactly as the event program promises.
4. **An AI judging panel, running in parallel** — six code-neutral, AI-neutral civic personas (including Data Provenance: can the numbers be traced back to the raw data?) score each team's written entry and README, then play out a bracket. **It decides nothing** and is never added to the vote. Its ranking is published beside the crowd's so the two can be compared.

The interesting output is not a winner. It is the agreement between the two: how closely a panel of language models tracked what Oak Park residents actually valued, and which of the six personas predicted the crowd best.

## Status

Implementation complete, pending the Netlify site connection.

- [Design spec](docs/superpowers/specs/2026-09-19-day-in-our-data-showcase-design.md)

## Get Started guides

Six attendee guides (`/start.html`, `/where-to-code.html`, `/cheatsheet.html`,
`/toolbox.html`, `/workflow.html`, `/testing.html`) cover first-time AI coding
setup, the Claude Code cheat sheet, connectors, plugins and skills, the
brainstorm-to-QA workflow, and automated testing.

They are **generated, not hand-written**:

- `guides/site.toml`: event details used on every page (`{event.<key>}`
  placeholders), plus nav order. Change the date, workspace link or credit
  instructions here once.
- `guides/pages/<slug>.toml`: one file per page, made of typed blocks
  (steps, cards, table, commands, flow, timeline...). The block types are
  documented at the top of `scripts/build_guides.py`.
- `python scripts/build_guides.py` rewrites `site/<slug>.html`; commit the
  result. `tests/test_guides.py` fails CI if the HTML is stale, if inline
  markup can inject HTML, or if anything shaped like an API key appears.

To add a page: create `guides/pages/<slug>.toml`, add the slug to
`[nav] pages`, rebuild, and add the path to `PAGES` in `tests/e2e/conftest.py`.
**Never put a key or token in these files; the repo is public.**

### Browser, accessibility and load tests

```bash
pip install -e ".[e2e]"
playwright install chromium            # or: export PW_CHROMIUM_PATH=/path/to/chrome
python -m pytest tests/e2e -v          # every page: no JS errors, fits 375px, axe clean, links resolve
```

`tests/load/locustfile.py` simulates a room of attendees; its docstring has
the command. Run it against a local build only; each request against the
free-plan Netlify site spends bandwidth.

## Deployment

The site publishes on Netlify's free plan from `site/`; see `netlify.toml`
for the build command and `docs/deployment-runbook.md` for setup. Three GitHub Actions workflows do the rest, all `workflow_dispatch`
(manually triggered) except the submissions sync, which also runs on a
schedule:

- **`sync-submissions.yml`** — polls the Netlify Forms API via
  `scripts/sync_netlify.py` and commits `data/submissions.json` and
  `data/id_map.json`. Runs every 15 minutes during event hours (Saturdays,
  16:00-21:59 UTC) and on demand. Needs the `NETLIFY_TOKEN` secret.
- **`judge.yml`** — runs the AI judging panel and commits `data/results/`.
  Defaults to a `mock` dry run (zero API spend); set `mock: false` on
  dispatch to spend real `claude-sonnet-5` tokens. Needs `ANTHROPIC_API_KEY`.
- **`tally.yml`** — reads ballots from Netlify Forms, holds them in memory,
  validates and counts them, and commits only `data/results/vote.json` and
  `comparison.json`. Ballots are never committed. Needs `NETLIFY_TOKEN` and
  `NETLIFY_SITE_ID`. One ballot counts per device (a random id `vote.js` stores
  in the browser).

Every bot commit carries `[skip netlify]`, so data changes never spend one of
the free plan's ~20 monthly deploys. Pages read `data/` live from
`raw.githubusercontent.com` (`site/scripts/data.js`) and fall back to the
`/data/` snapshot Netlify copies in at each deploy. `site/data/` is that
build-time copy and stays gitignored.

### Deleting a submission after voting opens

Ballots record the public id (`sub_003`) of each project a voter picked, so a
public id must mean the same project forever. `data/id_map.json` — written and
committed by `sync-submissions.yml` — pins each Netlify submission to the
number it was issued, and that number is never reused, even after the
submission is deleted.

**Do not hand-edit `data/id_map.json` or `data/submissions.json`, and do not
delete a submission from Netlify after the showcase publishes without checking
the tally afterwards.** If that mapping is ever bypassed or lost, the ids shift
down, ballots cast for one project start counting for another, and nothing
errors — the awards are simply wrong. The safe way to remove a spam entry once
voting has begun is to leave it in place and exclude it at the tally, or to
delete it and confirm `data/id_map.json` still holds its old number.

## Bulk-loading projects from Civic Spark

For teams that built in Civic Spark but never pressed "Enter project".
Full step-by-step, written for someone who has not used the repo before:
**[`docs/bulk-load-guide.md`](docs/bulk-load-guide.md)**.

Entries go in through Netlify Forms, not into `data/` directly: every sync
rebuilds `data/submissions.json` from Netlify, so a hand-added entry would be
overwritten. `scripts/bulk_submit.py` posts one CSV row per project to the
live site's `submission` form, exactly as the browser form does, zip included.
It needs only Python's standard library.

1. Download each team's project zip from Civic Spark (8 MB maximum; larger
   ones go in as a Drive or Dropbox link in `large_file_url`).
2. Copy [`docs/bulk-load-template.csv`](docs/bulk-load-template.csv), delete
   the example row, and add one row per project. `artifact_path` is the zip's
   path relative to the CSV.
3. Check without sending anything:
   ```
   python scripts/bulk_submit.py path/to/entries.csv
   ```
   Every row prints `READY`, `SKIP` (already entered) or `FIX` (with the
   reason). Nothing is sent while any row says `FIX`.
4. Send one row first, confirm it under Netlify → Forms → submission (and
   check the **Spam** tab), then send the rest:
   ```
   python scripts/bulk_submit.py path/to/entries.csv --send
   ```
5. Run **Actions → Sync Netlify submissions → Run workflow** and confirm the
   new projects appear in the gallery.

Re-running is safe and never loses a submission. A row is skipped if its team
and title are already on the site or were already sent from that CSV. Each
successful send is recorded in `<csv name>.sent.json` beside the CSV, which
covers the gap before the next sync; do not delete that file. A failed row is
retried on the next run. The script only ever adds entries. The one way an
entry goes missing is Netlify flagging it as spam, because the sync reads only
accepted entries: check the Spam tab after every batch.

## Re-running the AI judging

Re-judging scores **every** synced project again and replaces
`data/results/bracket.json` and `scores.json`. It never removes a submission.
It calls the Claude API and costs money on every run that gets past the first
API call, so run it once per batch of new entries.

1. **Sync first.** Actions → **Sync Netlify submissions** → Run workflow →
   wait for the green check. Judging only sees projects already in
   `data/submissions.json`.
2. Actions → **Run AI judging panel** → Run workflow, branch `main`.
3. **Untick "Dry run with no API calls"**, then click **Run workflow**.
   Ticked, it is a free mock run and judges nothing for real.
4. When it finishes, open the **Run the panel** step. It should end with
   `README read for X of Y submissions` and `Wrote results to data/results`,
   where Y is the number of projects in the gallery. The bracket shows on
   `/results.html` within about 5 minutes, with no deploy needed.
5. If voting has happened, run Actions → **Tally participant vote** so the
   vote and the new bracket appear side by side. Do not use the event-day
   **2 - Close voting** button for this: it re-runs (and pays for) the
   judging again.

If the run fails, the last line of **Run the panel** says why:

| Message | Fix |
|---|---|
| `credit balance is too low` | Add credit under Plans & Billing in the Console organization that owns the key |
| `not scoped to a workspace` | Replace the `ANTHROPIC_API_KEY` secret with a key created inside a Console workspace |
| `README read for 0 of 0 submissions` (green, but empty bracket) | The sync had not run; do step 1, then judge again |

## Ground rules inherited from the event

- Use public data and record where it came from.
- No confidential or sensitive personal information.
- AI-generated scores are labelled as such wherever they appear.
- Nothing here is an official Village of Oak Park product or position.

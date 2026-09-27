# Day in Our Data — Showcase

Companion site for [Day in Our Data](https://github.com/oak-park-cisc/Oak_Park_Day_in_our_Data), the Village of Oak Park civic hackathon run by the Civic Information Systems Commission.

**Event:** Saturday, October 3, 2026, 11 a.m. to 3 p.m., Dole Branch Library, 255 Augusta St., Oak Park, IL

## What this is

Three things the event program asks for and one experiment:

1. **Submission intake** — teams file their project: what they built, what it solves for, a repo or demo link, and an artifact.
2. **Public showcase** — everything every team produced, in one place.
3. **Participant vote** — attendees pick their top three with a ballot code issued at check-in. **The vote decides the awards**, exactly as the event program promises.
4. **An AI judging panel, running in parallel** — five code-neutral civic personas score the same submissions independently and play out a bracket. **It decides nothing.** Its ranking is published beside the crowd's so the two can be compared.

The interesting output is not a winner. It is the agreement between the two: how closely a panel of language models tracked what Oak Park residents actually valued, and which of the five personas predicted the crowd best.

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
  `comparison.json`. Ballots are never committed. Needs `NETLIFY_TOKEN` and the
  `BALLOT_CODES` secret (printed once, offline, by `python -m voting.generate_codes` — see
  that file's docstring; the code list itself never enters the repo).

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

## Ground rules inherited from the event

- Use public data and record where it came from.
- No confidential or sensitive personal information.
- AI-generated scores are labelled as such wherever they appear.
- Nothing here is an official Village of Oak Park product or position.

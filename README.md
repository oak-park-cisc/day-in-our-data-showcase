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

## Deployment

The site publishes on Netlify from `site/`; see `netlify.toml` for the build
command. Three GitHub Actions workflows do the rest, all `workflow_dispatch`
(manually triggered) except the submissions sync, which also runs on a
schedule:

- **`sync-submissions.yml`** — polls the Netlify Forms API via
  `scripts/sync_netlify.py` and commits `data/submissions.json` and
  `data/ballots.json`. Runs every 15 minutes during event hours (Saturdays,
  16:00-21:59 UTC) and on demand. Needs the `NETLIFY_TOKEN` secret.
- **`judge.yml`** — runs the AI judging panel and commits `data/results/`.
  Defaults to a `mock` dry run (zero API spend); set `mock: false` on
  dispatch to spend real `claude-sonnet-5` tokens. Needs `ANTHROPIC_API_KEY`.
- **`tally.yml`** — validates and counts the participant vote, and commits
  `data/results/vote.json` and `comparison.json`. Needs the `BALLOT_CODES`
  secret (printed once, offline, by `python -m voting.generate_codes` — see
  that file's docstring; the code list itself never enters the repo).

`data/` is committed (seeded with an empty `data/submissions.json` before
the event) and copied into the Netlify publish directory at build time,
because the site fetches everything from absolute `/data/...` paths.
`site/data/` is the build-time copy and stays gitignored. `data/ballots.json`
is deliberately stripped from that copy so cast ballots are never served at a
public URL.

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

# Deployment runbook

Everything needed to take this repository from merged code to a live site on
Netlify's **free** plan, accepting submissions and ballots. Written for the repo
owner; no prior context assumed. Design: `docs/superpowers/specs/2026-09-24-free-tier-deployment-design.md`.

## How the free plan is kept free

- The repo is **public**. Netlify's free plan cannot deploy a private,
  organization-owned repo.
- Netlify's free plan allows about **20 deploys a month** and pauses the site at
  the cap. So the bots (sync, judge, tally) commit with `[skip netlify]` and never
  deploy. Only commits that change the site's code deploy.
- Pages read their data **live from GitHub** (`raw.githubusercontent.com`, ~5
  minute cache). If GitHub is unreachable they fall back to the copy Netlify
  published at the last deploy.
- **Ballots are never committed.** The tally reads them from Netlify Forms and
  keeps them in memory. They remain visible in Netlify → Forms → ballot, to
  account holders only.

---

## 1. Connect the Netlify site

1. Netlify → **Add new site** → **Import an existing project** → select
   `oak-park-cisc/day-in-our-data-showcase`, branch **`main`**, on the **Free** plan.
2. Confirm the settings match `netlify.toml`: publish directory `site`, build
   command `mkdir -p data && rm -rf site/data && cp -r data site/data`.
3. Site settings → **Forms** → confirm form detection is enabled. Netlify detects
   the `submission` and `ballot` forms on the first successful deploy; the tally
   cannot run until the `ballot` form exists.
4. Deploy once. Submit one test entry through the submission form and confirm it
   appears under Site → Forms → submission.

## 2. Generate the ballot codes — offline

```
python -m voting.generate_codes --count <N>
```

Run it on a machine that will not commit its output. It prints the slip sheet and
the comma-joined string for the `BALLOT_CODES` secret. **Never paste the codes
into a file in this repository.** It is public.

## 3. Add the repository secrets

GitHub repo → Settings → Secrets and variables → Actions.

| Secret | Required | Used by |
|---|---|---|
| `NETLIFY_TOKEN` | yes | `sync-submissions.yml` **and `tally.yml`** (the tally reads ballots from Netlify). Create it at Netlify → User settings → Applications → New access token |
| `BALLOT_CODES` | yes | `tally.yml` |
| `ANTHROPIC_API_KEY` | only for the real judging run | `judge.yml` with `mock` unticked |
| `NETLIFY_SITE_ID` | only if needed | Set it only if a run fails with "Multiple Netlify forms named ... found" |

## 4. Verify the pipeline before the event

**Sync.** Actions → "Sync Netlify submissions" → Run workflow. Confirm it commits
`data/submissions.json` and `data/id_map.json`, and then check two things:
- Netlify → Deploys shows **no new deploy** for that commit (`[skip netlify]` is
  honoured).
- Within ~5 minutes the test entry appears in the gallery on the live site.

**Judging dry run.** Actions → "Run AI judging panel" → Run workflow, leaving
`mock` at its default `true`. Zero API spend. Confirm `results.html` shows the
bracket within ~5 minutes, again with no new deploy.

**Tally.** Visit `vote.html`, cast one ballot with a code from your slip sheet,
then Actions → `tally.yml` → Run workflow. It needs `data/submissions.json` and
the `NETLIFY_TOKEN` secret, and it fails with one clear line if either is missing.

## 5. Custom domain (optional)

Your DNS is on Cloudflare, on an account that also runs other sites. This adds
**one** record and changes nothing that exists.

1. Netlify → Domain management → **Add a domain** → `<subdomain>.<your-domain>`.
2. Cloudflare → your domain → DNS → **Add record**: type `CNAME`, name
   `<subdomain>`, target `<your-site>.netlify.app`, proxy status **DNS only**
   (grey cloud). Do not proxy it: Netlify needs to issue its own certificate.
3. Wait for Netlify to show the certificate as provisioned (minutes, occasionally
   longer).

No deploy is needed for this.

## 6. During and after the event

`sync-submissions.yml` runs every 15 minutes on Saturdays 16:00–21:59 UTC
(11:00 a.m.–4:59 p.m. Central) and on demand. New projects show on the site
within ~5 minutes of each sync.

After voting closes:
1. Run `judge.yml` with **`mock` unticked**. This is the only step that spends
   money, roughly $2 at `claude-sonnet-5` for a 20-project event.
2. Run `tally.yml`.
3. Netlify → Deploys → **Trigger deploy** once, so the fallback snapshot matches
   the published result.

## 7. Teardown — order matters

When the site is retired, **delete the Cloudflare CNAME first, then the Netlify
site.** A CNAME left pointing at a deleted Netlify site can be claimed by someone
else, who could then serve their content under your domain.

## Optional: protect `main`

Public repos get branch protection for free: Settings → Branches → add a rule for
`main` requiring a pull request. The bots push directly to `main`, so if you
enable this, allow GitHub Actions to bypass it, or they will fail.

---

## Checks that could not be made without a live site

These are tested against fakes only. One real sync clears the first three.

- **`created_at`** is assumed to be the Netlify submission timestamp field.
- **Artifact upload field shape**: the sync accepts both a URL string and
  `{url, filename, size}`.
- **Pagination**: pages until a short page returns.
- **`results.html` tie chips and notices** have never been seen rendered. On a
  low-turnout run most projects tie at zero, so many rows carry a "tied" chip;
  check that it reads well.

## Two things to know before you run this for real

**Never delete a Netlify form submission after the showcase publishes.** Public
ids are held stable by `data/id_map.json`, but don't rely on that if the map is
ever lost.

**One winner, no gift cards** (spec §1.2, amended 2026-09-21). A tie for first is
published as a shared win. The cut is `voting.ranking.DEFAULT_AWARD_COUNT`, now `1`.

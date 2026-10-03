# Bulk-loading Civic Spark projects and re-running AI judging

For projects that were built in Civic Spark but never entered through the
"Enter project" form. You fill one spreadsheet row per project, a script
submits each row through the live site's form (exactly as if the team had
pressed "Enter project"), and then you re-run the AI judging panel.

Nothing here touches Netlify settings, and nothing is deleted. Entries already
on the site are skipped automatically, so the script is safe to re-run.

Time: about 10 minutes of setup, then about 5 minutes per project to gather
its details, then 10–20 minutes for judging.

---

## Part 0 — What you need (once)

1. **GitHub access.** A GitHub account with **Write** access to
   `oak-park-cisc/day-in-our-data-showcase`. Test it: open
   https://github.com/oak-park-cisc/day-in-our-data-showcase/actions/workflows/judge.yml
   and check that a **Run workflow** button appears on the right. No button
   means ask the site owner to add you.
2. **Python 3.11 or newer.** Open a terminal (Mac: Terminal; Windows:
   PowerShell) and run:
   ```
   python --version
   ```
   On a Mac, if that fails, try `python3 --version` and use `python3` wherever
   this guide says `python`. If neither works, install Python from
   https://www.python.org/downloads/ and open a **new** terminal.
3. **Git.** Run `git --version`. If it fails, install Git from
   https://git-scm.com/downloads, or skip it and use step 4's ZIP option.
4. **A copy of the repository.** In the terminal:
   ```
   git clone https://github.com/oak-park-cisc/day-in-our-data-showcase.git
   cd day-in-our-data-showcase
   ```
   No Git? On the repository page click the green **Code** button →
   **Download ZIP**, unzip it, and `cd` into the unzipped folder.

   Already have a copy? Update it instead: `cd day-in-our-data-showcase` then
   `git pull`.

The script uses only Python's standard library. There is nothing to
`pip install`.

---

## Part 1 — Gather each project from Civic Spark

Make a working folder **outside** the repository, for example
`~/Desktop/bulk-load/`, with a subfolder `zips/` inside it.

For **each** project that was not entered:

1. **Download the project zip** from Civic Spark (https://day-in-our-data.fly.dev/),
   the same way teams were told to in the Start guide ("Save your work as a
   zip"). If you do not have access to a team's workspace, ask the Civic Spark
   admin to download it.
2. **Check the size.** It must be **8 MB or less**. If it is bigger, upload
   it to Google Drive or Dropbox, set sharing to "anyone with the link", and
   keep that link for the `large_file_url` column instead.
3. **Rename the zip** to something simple with no spaces, like
   `team-transit.zip`, and put it in `bulk-load/zips/`.
4. **Open the zip and find the README** (`README.md` near the top). The AI
   judges read it, so it matters more than anything else in the zip. If the
   team never wrote one, the judges score from the text you type in the
   spreadsheet alone. That is allowed, but the project will score lower.
5. **Note these details** (from the README, the team, or the table host):
   - Team name
   - Project title
   - **What did you build?** Two or three sentences.
   - **What does it solve for?** Who has the problem and what they can do now.
   - **How did you get from the raw data to the result?** Which dataset, what
     was done to it, where AI helped.
   - **Which starter project** (see the list in Part 2, step 3).
   - A GitHub link, a demo link, or both, if any. Each must start with
     `https://`. Only use a demo link if it opens in a private browser window
     without signing in.

Write only what the team actually built. The judges are told the text comes
from the team.

---

## Part 2 — Fill in the spreadsheet

1. Copy `docs/bulk-load-template.csv` from the repository into your
   `bulk-load/` folder and rename it `entries.csv`.
2. Open it in Excel, Numbers, or Google Sheets (Google Sheets: File → Import,
   then later File → Download → CSV).
3. **Delete the "Example Team" row**, then add one row per project:

   | Column | What to put | Required |
   |---|---|---|
   | `team_name` | Team name | yes |
   | `project_title` | Project title | yes |
   | `description` | What did you build? | yes |
   | `solves_for` | What does it solve for? | yes |
   | `data_steps` | From raw data to result | yes |
   | `starter_project` | One code from the list below, typed exactly | yes |
   | `repo_url` | GitHub link, or blank | no |
   | `demo_url` | Demo link, or blank | no |
   | `large_file_url` | Drive/Dropbox link if the zip is over 8 MB, or blank | no |
   | `artifact_path` | `zips/<the zip's file name>`, or blank | no |

   `starter_project` codes:
   ```
   01-is-my-assessment-fair
   02-where-does-my-tax-dollar-go
   03-where-is-business-activity-changing
   04-can-a-kid-bike-to-school-safely
   05-can-i-park-here-right-now
   06-which-bus-stops-need-help
   07-are-the-worst-alleys-getting-fixed
   08-build-the-oak-park-transit-dashboard
   09-oak-park-over-time
   10-how-are-our-schools-doing
   11-how-resilient-is-our-urban-forest
   12-build-an-architecture-walking-tour
   13-what-do-our-commissions-do
   14-oak-park-crime-explorer
   15-what-does-echo-see
   pitch-your-own
   ```
4. **Save as CSV** (Excel: File → Save As → "CSV UTF-8"). Keep the header row
   exactly as it is.

---

## Part 3 — Check, then send

All commands run from inside the `day-in-our-data-showcase` folder. Replace
the path with wherever your `entries.csv` is.

1. **Check only. Nothing is sent:**
   ```
   python scripts/bulk_submit.py ~/Desktop/bulk-load/entries.csv
   ```
   Windows example: `python scripts\bulk_submit.py $HOME\Desktop\bulk-load\entries.csv`

   Each row prints one of:
   - `READY`: good to send.
   - `SKIP`: that team and title are already on the site. Nothing to do.
   - `FIX`: the lines under it say what is wrong. Fix the spreadsheet, save,
     and run the check again. **Nothing is sent while any row says FIX.**

   It ends with `Check passed. N row(s) would be sent.`

2. **Send one project first.** Make a copy of `entries.csv` with only the
   header and your first project, then:
   ```
   python scripts/bulk_submit.py ~/Desktop/bulk-load/one.csv --send
   ```
   You should see `SENT row 2 (HTTP 200)`.

3. **Confirm that one arrived.** If you have Netlify access: app.netlify.com →
   the site → **Forms** → **submission**. The new entry should be at the top.
   **Also check the Spam tab** on that same page. Netlify sometimes flags
   scripted entries as spam. If it is there, open it and mark it **Not spam**.
   No Netlify access? Skip to Part 4, step 1, and look for it in the gallery.

4. **Send the rest:**
   ```
   python scripts/bulk_submit.py ~/Desktop/bulk-load/entries.csv --send
   ```
   The project you already sent shows `SKIP` and is not sent twice. It ends
   with `N sent, 0 failed.` If any row says `ERROR`, run the same command
   again: rows that already went through are skipped.

---

## Part 4 — Pull the projects into the site

1. Open
   https://github.com/oak-park-cisc/day-in-our-data-showcase/actions/workflows/sync-submissions.yml
2. Click **Run workflow** → leave `main` → click the green **Run workflow**.
3. Refresh after about 20 seconds. Wait for the **green check**.
4. Within about 5 minutes the new projects appear in the gallery at
   https://oakparkciscdiod.netlify.app/. Count them: the total should be the
   old count plus the number you sent. If one is missing, check Netlify's
   Spam tab (Part 3, step 3) and run this part again.

---

## Part 5 — Re-run the AI judging

This calls the Claude API and **costs money** (the event's Anthropic account).
It re-judges **every** project, old and new, and replaces the previous
bracket.

1. Open
   https://github.com/oak-park-cisc/day-in-our-data-showcase/actions/workflows/judge.yml
2. Click **Run workflow**. Leave `main`.
3. **Untick "Dry run with no API calls".** If it stays ticked, nothing is
   really judged.
4. Click the green **Run workflow**.
5. Refresh. A run with a yellow dot appears. Click it, then click **judge**
   to watch. Expect roughly 2 minutes per project.
6. When it shows a **green check**, open the **Run the panel** step. It
   should say `README read for X of Y submissions` and `Wrote results to
   data/results`. Y must equal the number of projects in the gallery.

### If the judging run fails (red ✕)

Click it, open **Run the panel**, and scroll to the last line:

| Last line says | Meaning | Fix |
|---|---|---|
| `credit balance is too low` | The Anthropic account is out of credit | Add credit in console.anthropic.com → Plans & Billing, then re-run step 1–4 |
| `not scoped to a workspace` | The API key is not tied to a workspace | Site owner replaces the `ANTHROPIC_API_KEY` secret with a key created inside a workspace |
| anything else | — | Send the run's link to the site owner |

Do not press it repeatedly: every run that gets past the first API call is
charged.

---

## Part 6 — Results page

The results page (`/results.html`) shows the AI bracket **next to** the
participant vote, so it stays on "Results are not available yet" until the
vote is tallied too. When voting has happened, run
https://github.com/oak-park-cisc/day-in-our-data-showcase/actions/workflows/tally.yml
(**Run workflow** → `main` → **Run workflow**). Do not use the event-day
"2 - Close voting" button for this: it would run (and pay for) the AI judging
a second time.

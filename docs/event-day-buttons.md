# Event day: the two buttons

On Saturday, whoever is running the event presses **two buttons**, both in
GitHub. You do not need Netlify, a terminal, or any passwords beyond your own
GitHub sign-in.

| Button | Press it when | Takes about |
|---|---|---|
| **1 - Open voting** | Submissions are closed, just before you announce voting | 2 minutes |
| **2 - Close voting** | Voting has ended | 15–25 minutes |

## Before Saturday (once)

- You need a GitHub account with **Write** access to
  `oak-park-cisc/day-in-our-data-showcase`. Ask the site owner to add you
  (Settings → Collaborators and teams). Check you can see a green
  **Run workflow** button on the page below.
- Bookmark this page. It is the only link you need:
  **https://github.com/oak-park-cisc/day-in-our-data-showcase/actions/workflows/event-day.yml**
- A laptop is easiest. On a phone, open the link in the browser rather than
  the GitHub app.

## How to press a button

1. Open the bookmarked page and sign in to GitHub if asked.
2. On the right, click **Run workflow**. A small panel opens.
3. Leave **Use workflow from** set to `main`.
4. Under **Which step?**, pick the step from the list:
   - `1 - Open voting (sync projects, then deploy)`, or
   - `2 - Close voting (AI judging, tally the vote, then deploy)`
5. Click the green **Run workflow** button in the panel.
6. Refresh the page after a few seconds. A new run appears at the top with a
   yellow dot while it works. Click it to watch.

When it finishes, the dot turns into a **green check**, and the run page shows
a **Summary** table: every row should say ✅ done (rows marked ➖ are not part
of that step). The summary links to the live site.

(The list has a third entry, `0 - Rehearsal`. It is for the site owner's
testing. Ignore it on Saturday.)

## What each button does

**1 - Open voting**
- Pulls every project entered so far into the site.
- Deploys the site so the ballot page has a backup copy of the full project
  list, in case the library Wi-Fi gets throttled.
- Safe to press again if a late entry arrives. Each press uses one of the
  site's roughly 20 monthly deploys, so do not press it for fun.

**2 - Close voting**
- Pulls in any last projects.
- Runs the AI judging panel for real. **This costs about $3**, charged to the
  event's Anthropic account. It is the only step that spends money.
- Counts the ballots and publishes the winner on the results page.
- Deploys the site.
- **Press it once.** Pressing it again runs (and pays for) the AI judging a
  second time.

## If something goes wrong

- **A red ✕ on the run:** open it and click **Re-run failed jobs** (top
  right). Try once. If it fails again, message the site owner with the link
  to the run page. Nothing is lost by waiting.
- **The summary says the vote was published but AI judging failed:** fine.
  The winner is decided by the vote, which is already on the results page. The
  AI comparison can be added later by the site owner.
- **You pressed the wrong step:** step 1 by mistake does no harm. If you
  pressed step 2 before voting ended, message the site owner; do not press it
  again yet.
- **You cannot see the Run workflow button:** you are not signed in, or you
  do not have Write access yet.

## You never need to

- Open Netlify or trigger a deploy yourself.
- Run any other workflow on the Actions page. The other entries there are the
  pieces this button runs for you.
- Handle ballot codes, API keys, or tokens. They are stored as GitHub secrets
  and never appear on screen.

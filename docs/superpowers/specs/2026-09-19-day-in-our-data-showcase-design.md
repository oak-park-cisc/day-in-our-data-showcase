# Day in Our Data — Showcase, Participant Vote, and AI Judging Panel

**Date:** 2026-09-19
**Status:** Approved design, ready for implementation planning
**Event:** Saturday, October 3, 2026, 11:00–15:00, Dole Branch Library, Oak Park, IL
**Target repo:** `oak-park-cisc/day-in-our-data-showcase`

---

## 1. Context

The Village of Oak Park's Civic Information Systems Commission (CISC) runs *Day in Our Data*, a one-day civic hackathon. The existing repo, `oak-park-cisc/Oak_Park_Day_in_our_Data`, holds fifteen starter-project cards, a cached civic data catalogue, and the event program.

`event-program.md` lists two unmet needs this project fills:

- *What We Need Before the Event:* "A shared repository or website for project information and results."
- *Decisions for CISC:* "Confirm where project information and results will be published."

This project delivers that site: submission intake, a public showcase, the participant vote, and an independent AI judging panel published alongside for comparison.

### 1.1 Relationship to the published plan

The event program states:

> "Nothing is judged on the day. After the event, CISC publishes a showcase of what every team produced. Participants then vote on their favorites from the showcase, and the top teams receive gift cards and are invited to present their work at a later CISC meeting."

**This design implements that plan as written.** The participant vote determines gift-card recipients. No rule changes, no CISC governance decision, and nothing participants were not already told.

The AI panel runs **in parallel and decides nothing**. It scores the same submissions independently and its ranking is published beside the crowd's, along with a measure of how closely the two agree. It is an experiment reported as a finding, not an authority.

Two consequences worth stating plainly:

1. **No committee member has to judge.** This was the constraint that prompted the design: nobody on CISC wants to judge, and under this model nobody has to. The participants do the judging, as the program already promised, and the AI panel costs only compute.
2. **No appeals path is required.** A team that dislikes its AI score can point at the transcripts (§5.5) and disagree in public. Nothing is at stake in that number, so nothing has to adjudicate it.

CISC should still be *told* that an AI panel will be published alongside the vote, and the showcase must label those scores as AI-generated at the point of display (§10.6). That is disclosure, not approval.

---

## 2. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Participant vote decides awards; AI panel runs in parallel and decides nothing | Implements the published plan. Removes the governance dependency and the appeals problem entirely. |
| D2 | Links + artifacts; no code execution | Ships in the window. Arbitrary execution on a public Village-adjacent site is out of scope, permanently. |
| D3 | Score-to-seed, then real head-to-head | LLMs compare more reliably than they score absolutely. Yields legible scores *and* a genuine tournament. |
| D4 | Netlify (site + Forms) + GitHub Actions (judging and tally) | Forms are free and unlimited with native file upload. Judging exceeds any serverless timeout, so it runs in Actions. |
| D5 | Five code-neutral civic personas | An odd panel resolves every matchup by majority. The event states coding is optional. |
| D6 | New repo in `oak-park-cisc` | The data repo's large GeoJSON/CSV payload would be re-cloned on every Netlify build. |
| D7 | Design derived from the event logo, not from oak-park.us | Avoids implying an official Village product; the logo is the stronger identity. |
| D8 | No red in the UI palette; green carries "advancing" | User decision. Grounded in Oak Park's canopy. |
| D9 | Judging harness in Python; site is plain static HTML/CSS/JS | Python matches the upstream repo's `data/scripts/` and the author's primary language. Two pages reading committed JSON need no framework. |
| D10 | Ballot codes issued at check-in; top-3 approval voting | Check-in is already staffed at 10:30, so distribution costs nothing. Ranking fourteen projects is too much friction; picking three is not. |
| D11 | Ballot code list never enters the public repo | The repo is public. Codes live only as a GitHub Actions secret and on the printed slips. |

### 2.1 Out of scope

- Executing participant-submitted code.
- Live sandboxed preview of uploaded HTML (deferred to Phase 2, §11).
- Participant accounts or authentication.
- Editing or deleting a submission after it is filed (admin-only, by hand).

---

## 3. Architecture

```
oak-park-cisc/day-in-our-data-showcase
├── site/                       # static; Netlify publish directory
│   ├── index.html              # Tab 1 — submit + showcase gallery
│   ├── vote.html               # Tab 2 — ballot-code vote, top-3
│   ├── results.html            # Tab 3 — crowd vs. AI comparison + bracket
│   ├── assets/logo.svg         # rebuilt from upstream scene.json
│   └── styles/
├── judging/
│   ├── personas/               # 5 judge prompts, one markdown file each
│   ├── rubric.md               # public, human-readable
│   ├── schema/
│   │   ├── score.schema.json
│   │   └── matchup.schema.json
│   ├── run_panel.py            # dispatch, validate, aggregate
│   └── bracket.py              # seeding, byes, majority resolution
├── voting/
│   ├── generate_codes.py       # offline; prints slips, emits the secret
│   └── tally.py                # validate ballots, count, correlate
├── data/
│   ├── submissions.json
│   └── results/
│       ├── scores.json         # AI pass 1
│       ├── bracket.json        # AI pass 2
│       ├── vote.json           # crowd tally
│       ├── comparison.json     # agreement statistics
│       └── transcripts/        # every prompt + raw response
├── tests/fixtures/
├── .github/workflows/
│   ├── sync-submissions.yml    # Forms API → submissions.json
│   ├── judge.yml               # workflow_dispatch only
│   ├── tally.yml               # workflow_dispatch only
│   └── ci.yml                  # tests, mock LLM, zero API spend
└── docs/superpowers/specs/
```

### 3.1 Data flow

1. **Submit.** A team fills the Netlify Form: team name, project title, description, what it solves for, starter project chosen (or *pitch your own*), repo URL, demo URL, one artifact upload, and a large-file link fallback (§3.3). Netlify stores the submission and the file.
2. **Sync.** `sync-submissions.yml` polls the Netlify Forms API, writes `data/submissions.json`, records artifact URLs, and commits. Netlify rebuilds; the gallery updates. Runs on a schedule during the event and on demand.
3. **Vote.** Attendees enter their ballot code at `/vote` and pick three projects. Ballots land in a second Netlify Form.
4. **Judge.** After submissions close, an admin dispatches `judge.yml`. It assembles per-team evidence, runs pass 1 and pass 2 (§5), and commits `scores.json`, `bracket.json`, and transcripts.
5. **Tally.** An admin dispatches `tally.yml`. It validates ballots against the secret code list, counts approvals, computes the agreement statistics (§7), and commits `vote.json` and `comparison.json`.
6. **Publish.** Netlify rebuilds. `results.html` goes live.

Steps 4 and 5 are independent and can run in either order. The AI panel never reads vote data, and the tally never reads AI output except to compute correlation — so neither can influence the other.

### 3.2 Why judging is not on Netlify

Netlify Functions cap near 10s (26s synchronous ceiling). The panel is ~200 LLM calls across minutes of wall time. GitHub Actions has no comparable limit, keeps the run off any personal machine, and produces an auditable log.

### 3.3 Netlify Forms — verified constraints (2026-09-19)

| Fact | Value | Design response |
|---|---|---|
| Forms on credit-based plans | Free and unlimited, no per-submission cost | No tier concern at ~14 teams |
| **Max form request** | **8 MB total** | One artifact upload, plus a `large_file_url` text field for anything bigger |
| Upload timeout | 30 seconds | Acceptable |
| Files per field | One | Single artifact field by design |
| Uploaded file URLs | Public; exposed via API and CSV export | Link to them directly; never mirror into the repo |
| Retention | None specified; Netlify advises exporting and deleting PII | Post-event cleanup step (§13) |

Netlify has moved to a credits-based pricing model (production deploys 15 credits, bandwidth 20 credits/GB). Forms being free and unlimited is the fact that matters here; bandwidth at this scale is negligible.

Netlify Forms was chosen over Airtable, Google Forms, and GitHub Issue Forms on one criterion: **it requires no account to submit.** At an event whose premise is that non-coders belong, an account barrier is disqualifying.

---

## 4. Data contracts

### 4.1 Submission

```json
{
  "id": "sub_003",
  "anon_id": "P-07",
  "team_name": "string",
  "project_title": "string",
  "description": "string",
  "solves_for": "string",
  "starter_project": "04-can-a-kid-bike-to-school-safely | pitch-your-own",
  "repo_url": "string | null",
  "demo_url": "string | null",
  "artifacts": [{ "filename": "string", "url": "string", "bytes": 0 }],
  "large_file_url": "string | null",
  "submitted_at": "ISO-8601"
}
```

`anon_id` is what judges see in pass 1. The mapping lives only in `submissions.json`, never in a prompt.

### 4.2 Score (AI pass 1) — `score.schema.json`

```json
{
  "persona": "civic-impact",
  "anon_id": "P-07",
  "score": 4,
  "justification": "string, max 2 sentences",
  "evidence": ["string, quoted or pointed at"],
  "reduced_evidence": false
}
```

`evidence` must be non-empty. An empty array fails validation (§8).

### 4.3 Matchup (AI pass 2) — `matchup.schema.json`

```json
{
  "matchup_id": "r1-m3",
  "round": 1,
  "a": "P-07",
  "b": "P-12",
  "persona": "continuation",
  "winner": "P-07",
  "reasoning": "string",
  "swap_confirmed": true
}
```

### 4.4 Ballot

```json
{
  "code": "string, validated then discarded",
  "picks": ["sub_003", "sub_009", "sub_011"],
  "cast_at": "ISO-8601"
}
```

Codes are never written to `vote.json`. The tally records only counts.

---

## 5. AI judging methodology

The panel decides nothing. Its methodology still has to be sound, because a sloppy panel makes the comparison in §7 meaningless.

### 5.1 Rubric — five personas, 1–5 each with justification

| Persona | Question |
|---|---|
| Civic Impact | Does this answer a question a real Oak Park resident has? |
| Data Integrity | Are sources named and limits stated? |
| Usability & Access | Can a non-technical resident actually use this? |
| Craft | Is it finished and working — in whatever form it takes? |
| Continuation | Could CISC or Village staff pick this up Monday? |

Every persona prompt states explicitly that **code is not required**, and that a cleaned dataset, a map, a chart, or a well-documented question must not be penalised for lacking one. The event program guarantees this: *"Coding is optional: every starter project has work for people who never touch a keyboard."*

### 5.2 Pass 1 — blind scoring

Each of 5 personas scores each of N teams. Judges receive `anon_id`, never team names. In a village, model priors may well recognise local names; blinding removes that channel, and independence from the crowd is what makes §7 worth reporting. Mean score across personas sets the seed.

Seeding ties break in this order: (1) higher Civic Impact score, (2) higher Data Integrity score, (3) earlier `submitted_at`. Deterministic and stated in advance, so no tie is resolved by list order.

### 5.3 Pass 2 — position-swapped head-to-head

Each matchup is run twice per persona, with A and B swapped. A vote counts only if it survives the swap; otherwise it is recorded as an abstention. LLM position bias in pairwise comparison is well-documented and would otherwise silently determine outcomes. The matchup resolves by majority of surviving votes.

### 5.4 Cost

At ~14 teams: 5 × 14 = 70 scoring calls, plus 5 × 13 × 2 = 130 matchup calls. **~200 calls**, roughly 1–2M input tokens. Single-digit dollars.

This is a deliberate exception to the standing "no per-token API charges in CI" rule: here the API spend *is* the product, it is bounded, and it occurs only on manual dispatch. Routine CI uses the mock (§9) and spends nothing. `event-program.md` already lists "LLM credits" as a budgeted CISC decision.

### 5.5 Transcripts

Every prompt and raw response is committed to `data/results/transcripts/`. Any team can read exactly what the panel saw and said. With nothing at stake in the number, this is documentation rather than defence — and it is what makes the experiment reproducible by anyone who wants to check it.

---

## 6. Participant voting

### 6.1 Ballot codes

`voting/generate_codes.py` runs offline before the event. It emits:

- A printable sheet of unique codes for check-in slips.
- The code list as a single value to be stored as the `BALLOT_CODES` GitHub Actions secret.

**The code list never enters the repo.** The repo is public; committed codes would be usable by anyone. Codes are long enough that guessing is impractical, and no hash list is published — validation happens only inside the tally job, where the secret is available.

### 6.2 Casting

`/vote` asks for a ballot code and three project picks from the showcase, unranked. Submission goes to a second Netlify Form. Voters see a confirmation; validity is determined at tally time, not on submit. This is a deliberate simplification — adding a Netlify Function for instant code validation is a Phase 2 nicety, not a launch requirement.

Self-voting is not prevented. Teams voting for themselves is expected, roughly symmetric across teams, and not worth the friction of policing.

### 6.3 Tally

`voting/tally.py` validates each ballot against the secret list, discards invalid codes, keeps only the first ballot per code, and counts approvals per project.

Because picks are unranked, there is no principled way to break a tie in approval count from the ballot data — so the tally does not invent one. Tied projects share a rank and are displayed as tied. If a tie falls on a gift-card boundary, it is flagged in `vote.json` and **CISC decides**, which is the correct place for that judgement. The AI bracket is never used to break it; letting it do so would quietly make the panel authoritative, which D1 rules out.

Codes are discarded after validation. `vote.json` contains counts only — no code, no voter identity.

### 6.4 Turnout floor

If fewer than 10 valid ballots are cast, the crowd ranking is published as **indicative only**, the sample size is stated on the page, and the correlation in §7 is reported with an explicit caveat rather than as a result. A rank correlation over a handful of ballots is noise, and presenting it as a finding at a data event would be the wrong lesson.

---

## 7. The comparison

This is the project's actual output, and the most interesting page on the site.

- **Crowd ranking** — projects ordered by approval count.
- **AI ranking** — projects ordered by bracket finish, with mean persona score as the secondary view.
- **Agreement** — Spearman's rank correlation between the two orderings, reported with n and an honest note that n ≈ 14 is a small sample.
- **Per-persona agreement** — each persona's ranking correlated against the crowd separately, answering: *which of the five judges best predicted what residents actually valued?*

That last number is the finding worth presenting at a CISC meeting. It is a real result about machine and human judgement, produced from the event's own data, at a civic data hackathon — which is a better story than any winner announcement.

`comparison.json` carries the statistics; `results.html` renders them beside the bracket.

---

## 8. Error handling

| Condition | Behaviour |
|---|---|
| Malformed or schema-invalid judge JSON | One retry. Then recorded as abstention; matchup resolves on remaining votes. |
| Empty `evidence[]` | Treated as schema-invalid. Same path. |
| Vote flips under position swap | Abstention. Never counted. |
| All 5 personas abstain on a matchup | Higher seed advances. Logged and surfaced in the UI. |
| `repo_url` unreachable | Judge scores on description and artifacts; `reduced_evidence: true`, shown in the UI. Never silent. |
| Team count not a power of two | Top seeds receive byes. |
| Fewer than 4 submissions | Bracket degrades to a ranked list. Detected automatically. |
| Duplicate submission from one team | Latest wins. Prior retained in `transcripts/`. |
| Artifact over 8 MB | Rejected by Netlify at submit. Form copy directs the team to `large_file_url`. |
| Invalid ballot code | Discarded at tally. Counted and reported in aggregate, never per-voter. |
| Reused ballot code | First ballot kept, rest discarded. |
| Ballot referencing an unknown project id | Whole ballot discarded; counted in the invalid total. |
| Fewer than 10 valid ballots | §6.4 indicative-only path. |
| Netlify Forms API failure during sync | Action fails loudly; previous `submissions.json` remains valid. |

---

## 9. Testing

- Fixture-based, with a **mock LLM** returning canned JSON. Zero API spend in CI.
- Six synthetic submissions cover: a no-code dataset entry, a dead repo link, an empty description, a duplicate, a reduced-evidence case, and a non-power-of-two cohort.
- Ballot fixtures cover: valid, invalid code, reused code, unknown project id, and a below-floor turnout.
- Assertions on: seeding order and tie-breaks, bye placement, majority resolution, abstention handling, swap aggregation, schema validation of every judge response, approval counting, ballot de-duplication, and Spearman correlation against a hand-computed value.
- `ci.yml` runs on every push with `ANTHROPIC_API_KEY` unset, proving the mock path never reaches the network.

---

## 10. Visual design

### 10.1 Direction

The site does **not** mirror www.oak-park.us. It shares the Village's civic seriousness and accessibility posture while carrying the event's own identity, so it sits beside the Village site without implying it is an official Village product — a distinction the event's ground rules already draw: *"Nothing produced at the event is an official Village product or position."*

### 10.2 Signature — the bracket as Prairie art glass

Oak Park's most recognisable visual export is Prairie School art glass. Wright's Home and Studio is here; the repo's own starter project 12 covers 4,958 surveyed historic buildings. Prairie art glass is a geometric grid of rectangular panes joined by dark leaded cames. A tournament bracket is also a grid of rectangles joined by lines.

Matchup cells are panes. Connectors are cames, in `--ink`. The champion pane is `--glass` gold. Clicking a came opens the five personas' votes and reasoning for that matchup.

On `results.html` the crowd ranking sits beside the glass as a plain, quiet column — the contrast between the ornamented machine bracket and the unadorned human list is the page's argument, and the restraint is the point.

### 10.3 Palette

Derived from the upstream logo's `scene.json`, extended with greens drawn from Oak Park's canopy (starter project 11: 18,800 public trees against the 10-20-30 rule). Amber and green are the canonical Prairie art-glass pair, so the greens reinforce the signature rather than sitting on top of it.

| Token | Hex | Role |
|---|---|---|
| `--ink` | `#102a56` | Text, header, leaded cames |
| `--civic` | `#1559d6` | Links, primary action, data bars |
| `--canopy` | `#14503a` | Deep green — section heads, winner frames (9.5:1 on white) |
| `--leaf` | `#2d7a55` | Mid green — advancing state, live countdown (5.2:1, AA) |
| `--sprout` | `#7fb996` | Light green — pane tints |
| `--glass` | `#ffc629` | Champion pane and sun. Once per screen |
| `--paper` | `#eef2ef` | Pale green-gray ground |
| `--rule` | `#c9d3e4` | Hairlines |

**No red anywhere in the UI.** Green marks advancing; muted slate marks eliminated. Most brackets use red for knocked-out; dropping it removes the one unkind colour from a page that tells residents their project lost.

The upstream logo contains `#e53935` in its line-chart element. The logo is kept canonical — it is the event's published mark, and logos routinely carry a colour the UI palette does not.

### 10.4 Type

| Face | Role | Reason |
|---|---|---|
| Jost | Display, 700/800 | Geometric Futura lineage, period-correct to Prairie; closest free web face to the logo's Avenir Next 800 |
| Public Sans | Body | The US Web Design System typeface — civic seriousness and proven accessibility, without cloning any municipal CMS |
| IBM Plex Mono | Utility | Seeds, scores, provenance lines |

### 10.5 Hero

The logo is rebuilt as inline SVG from the upstream `scene.json`'s actual layer coordinates, and animated once on load: bars rise, the line draws, sun rays ease out. A day, in our data. `prefers-reduced-motion` is respected.

### 10.6 Quality floor

Responsive to mobile; visible keyboard focus; reduced motion respected; all colour pairs meet WCAG AA. Every AI-generated score is labelled as such at the point of display, and the results page states plainly that the participant vote determines awards.

---

## 11. Phase 2 — deferred

- **Sandboxed preview.** Teams' uploaded static HTML served live in a sandboxed iframe from a **second Netlify site on a separate origin**, with a strict CSP and a documented takedown path. Origin isolation is non-negotiable; same-origin rendering of participant HTML would expose the main site to stored XSS.
- **Instant ballot-code validation** via a Netlify Function (§6.2).

Both are deferred because neither is required for the event to work.

---

## 12. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Low voter turnout makes the crowd ranking noisy | Medium | §6.4 floor: publish as indicative, state n, caveat the correlation. |
| Ballot stuffing | Low | Codes issued in person at check-in, one ballot per code, list held only as an Actions secret (D11). |
| Artifacts exceed the 8 MB form cap | Medium | `large_file_url` fallback field; form copy explains it before upload. |
| Uploaded artifact contains personal data | Medium | Ground rules already forbid it. Admin review before results publish; takedown path documented; post-event export-and-delete (§13). |
| AI panel output is embarrassing or unfair to a team | Low | It decides nothing, is labelled AI-generated, and ships with full transcripts. Worst case it is a bad prediction, publicly visible as such. |
| Too few submissions for a bracket | Low | Under 4, degrades to a ranked list automatically (§8). |
| Netlify credits model changes costs | Low | Forms free and unlimited; bandwidth negligible at this scale. Re-check before launch. |

---

## 13. Timeline

14 days to the event.

| Window | Work |
|---|---|
| Sept 19–21 | Implementation plan. CISC informed that an AI panel will be published alongside the vote. Ballot codes generated and slips printed. |
| Sept 22–26 | Site build: hero, submission form, showcase gallery. Netlify + Forms wired. Sync Action. |
| Sept 27–30 | Judging: personas, schemas, `run_panel.py`, `bracket.py`. Voting: `tally.py`. Fixtures and mock-LLM tests. |
| Oct 1–2 | `results.html` and the comparison. Full dry run on fixtures. Accessibility pass. Upstream repo README updated to link the site. |
| **Oct 3** | Event. Slips handed out at check-in. Sync Action runs live. |
| Oct 4–6 | Submissions close. Admin review. Voting window opens. |
| Oct 7–10 | Voting closes, `judge.yml` and `tally.yml` dispatched, results published. Netlify submissions exported and PII deleted. |

---

## 14. Open items

1. **Model choice for the panel** — resolve during planning.
2. **Submission close time** — end of event, or a grace window to the following day?
3. **Voting window length** — how long after the showcase publishes does voting stay open?
4. **Expected attendance** — determines how many ballot codes to print.
5. **Who runs the two dispatch jobs** — a named admin with repo write access.

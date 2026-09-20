# Day in Our Data — Showcase & AI Judging Site

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

This project delivers that site, plus an LLM judging panel that produces the final ranking.

### 1.1 Departure from the published plan — requires CISC approval

Both `README.md` and `event-program.md` currently state:

> "Nothing is judged on the day. After the event, CISC publishes a showcase of what every team produced. **Participants then vote on their favorites** from the showcase, and the top teams receive gift cards and are invited to present their work at a later CISC meeting."

This design **replaces participant voting with an LLM judge panel as the award mechanism.** That is a governance decision belonging to CISC, not a technical one.

**This is a hard prerequisite, not a caveat.** Before results are published, CISC must approve:

1. That an AI panel, not participant vote, determines gift-card recipients.
2. The published rubric (§5.1).
3. The appeals path and who adjudicates it.
4. The wording that labels all scores as AI-generated.

Both source documents must then be updated so participants are told the rules **before** they submit. Judging a cohort under rules they were not shown is the single largest reputational risk in this project.

If CISC declines, the fallback is one configuration change: the panel becomes advisory (per-project feedback published alongside each entry) and participant voting decides awards. The build supports this without rework.

---

## 2. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | AI panel decides the ranking | User decision, 2026-09-19. Gated on §1.1. |
| D2 | Links + artifacts; no code execution | Ships in the window. Arbitrary execution on a public Village-adjacent site is out of scope, permanently. |
| D3 | Score-to-seed, then real head-to-head | LLMs compare more reliably than they score absolutely. Yields legible scores *and* a genuine tournament. |
| D4 | Netlify (site + Forms) + GitHub Actions (judging) | Forms handles file upload natively. Judging exceeds any serverless timeout, so it runs in Actions. |
| D5 | Five code-neutral civic personas | An odd panel resolves every matchup by majority. The event states coding is optional. |
| D6 | New repo in `oak-park-cisc` | The data repo's large GeoJSON/CSV payload would be re-cloned on every Netlify build. |
| D7 | Design derived from the event logo, not from oak-park.us | Avoids implying an official Village product; the logo is the stronger identity. |
| D8 | No red in the UI palette; green carries "advancing" | User decision. Grounded in Oak Park's canopy. |
| D9 | Judging harness in Python; site is plain static HTML/CSS/JS | Python matches the upstream repo's `data/scripts/` and the author's primary language. The site needs no framework — two pages reading committed JSON. |

### 2.1 Out of scope

- Executing participant-submitted code.
- Live sandboxed preview of uploaded HTML (deferred to Phase 2, §9).
- Participant accounts or authentication.
- Editing or deleting a submission after it is filed (admin-only, by hand).

---

## 3. Architecture

```
oak-park-cisc/day-in-our-data-showcase
├── site/                       # static; Netlify publish directory
│   ├── index.html              # Tab 1 — submit + showcase gallery
│   ├── bracket.html            # Tab 2 — bracket + score cards
│   ├── assets/
│   │   └── logo.svg            # rebuilt from upstream scene.json
│   └── styles/
├── judging/
│   ├── personas/               # 5 judge prompts, one markdown file each
│   ├── rubric.md               # public, human-readable
│   ├── schema/
│   │   ├── score.schema.json
│   │   └── matchup.schema.json
│   ├── run_panel.py            # dispatch, validate, aggregate
│   └── bracket.py              # seeding, byes, majority resolution
├── data/
│   ├── submissions.json        # synced from Netlify Forms
│   └── results/
│       ├── scores.json         # pass 1
│       ├── bracket.json        # pass 2
│       └── transcripts/        # every prompt + raw response
├── tests/
│   └── fixtures/
├── .github/workflows/
│   ├── sync-submissions.yml    # Forms API → submissions.json
│   ├── judge.yml               # workflow_dispatch only
│   └── ci.yml                  # tests, mock LLM, zero API spend
└── docs/superpowers/specs/
```

### 3.1 Data flow

1. **Submit.** A team fills the Netlify Form: team name, project title, description, what it solves for, starter project chosen (or *pitch your own*), repo URL, demo URL, artifact uploads. Netlify stores the submission and the files.
2. **Sync.** `sync-submissions.yml` polls the Netlify Forms API, writes `data/submissions.json`, records artifact URLs, and commits. Netlify rebuilds; the gallery updates. Runs on a schedule during the event and on demand.
3. **Judge.** After submissions close, an admin dispatches `judge.yml` manually. It assembles per-team evidence (form fields, fetched repo README, artifact inventory), runs pass 1 and pass 2 (§5), writes `scores.json`, `bracket.json`, and transcripts, and commits.
4. **Publish.** Netlify rebuilds. Tab 2 goes live.

### 3.2 Why judging is not on Netlify

Netlify Functions cap near 10s (26s synchronous ceiling). The panel is ~200 LLM calls across minutes of wall time. Background Functions (15 min) are plan-gated and still tight. GitHub Actions has no comparable limit, keeps the run off any personal machine, and produces an auditable log.

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
  "submitted_at": "ISO-8601"
}
```

`anon_id` is what judges see in pass 1. The mapping lives only in `submissions.json`, never in a prompt.

### 4.2 Score (pass 1) — `score.schema.json`

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

`evidence` must be non-empty. An empty array fails validation (§6).

### 4.3 Matchup (pass 2) — `matchup.schema.json`

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

---

## 5. Judging methodology

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

Each of 5 personas scores each of N teams. Judges receive `anon_id`, never team names. In a village, model priors may well recognise local names; blinding removes that channel. Mean score across personas sets the seed.

Seeding ties break in this order: (1) higher Civic Impact score, (2) higher Data Integrity score, (3) earlier `submitted_at`. Deterministic and stated in advance, so no tie is resolved by chance or by list order.

### 5.3 Pass 2 — position-swapped head-to-head

Each matchup is run twice per persona, with A and B swapped. A vote counts only if it survives the swap; otherwise it is recorded as an abstention. LLM position bias in pairwise comparison is well-documented and would otherwise silently determine outcomes. The matchup resolves by majority of surviving votes.

### 5.4 Cost

At ~14 teams: 5 × 14 = 70 scoring calls, plus 5 × 13 × 2 = 130 matchup calls. **~200 calls**, roughly 1–2M input tokens. Single-digit dollars.

This is a deliberate exception to the standing "no per-token API charges in CI" rule: here the API spend *is* the product, it is bounded, and it occurs only on manual dispatch. Routine CI uses the mock (§7) and spends nothing. `event-program.md` already lists "LLM credits" as a budgeted CISC decision.

### 5.5 Transcripts

Every prompt and raw response is committed to `data/results/transcripts/`. A team that places ninth can read precisely why. Without this, an AI ranking is unanswerable, and an unanswerable ranking becomes a complaint to the Village rather than an appeal to the organisers.

---

## 6. Error handling

| Condition | Behaviour |
|---|---|
| Malformed or schema-invalid judge JSON | One retry. Then recorded as abstention; matchup resolves on remaining votes. |
| Empty `evidence[]` | Treated as schema-invalid. Same path. |
| Vote flips under position swap | Abstention. Never counted. |
| All 5 personas abstain on a matchup | Higher seed advances. Logged and surfaced in the UI. |
| `repo_url` unreachable | Judge scores on description and artifacts; `reduced_evidence: true`, shown in the UI. Never silent. |
| Team count not a power of two | Top seeds receive byes. |
| Duplicate submission from one team | Latest wins. Prior retained in `transcripts/`. |
| Netlify Forms API failure during sync | Action fails loudly; previous `submissions.json` remains valid. |

---

## 7. Testing

- Fixture-based, with a **mock LLM** returning canned JSON. Zero API spend in CI.
- Six synthetic submissions cover: a no-code dataset entry, a dead repo link, an empty description, a duplicate, a reduced-evidence case, and a non-power-of-two cohort.
- Assertions on: seeding order, bye placement, majority resolution, abstention handling, swap aggregation, and schema validation of every judge response.
- `ci.yml` runs on every push with `ANTHROPIC_API_KEY` unset, proving the mock path never reaches the network.

---

## 8. Visual design

### 8.1 Direction

The site does **not** mirror www.oak-park.us. It shares the Village's civic seriousness and accessibility posture while carrying the event's own identity, so it sits beside the Village site without implying it is an official Village product — a distinction the event's ground rules already draw: *"Nothing produced at the event is an official Village product or position."*

### 8.2 Signature — the bracket as Prairie art glass

Oak Park's most recognisable visual export is Prairie School art glass. Wright's Home and Studio is here; the repo's own starter project 12 covers 4,958 surveyed historic buildings. Prairie art glass is a geometric grid of rectangular panes joined by dark leaded cames. A tournament bracket is also a grid of rectangles joined by lines.

Matchup cells are panes. Connectors are cames, in `--ink`. The champion pane is `--glass` gold. Clicking a came opens the five personas' votes and reasoning for that matchup.

### 8.3 Palette

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

### 8.4 Type

| Face | Role | Reason |
|---|---|---|
| Jost | Display, 700/800 | Geometric Futura lineage, period-correct to Prairie; closest free web face to the logo's Avenir Next 800 |
| Public Sans | Body | The US Web Design System typeface — civic seriousness and proven accessibility, without cloning any municipal CMS |
| IBM Plex Mono | Utility | Seeds, scores, provenance lines |

### 8.5 Hero

The logo is rebuilt as inline SVG from the upstream `scene.json`'s actual layer coordinates, and animated once on load: bars rise, the line draws, sun rays ease out. A day, in our data. `prefers-reduced-motion` is respected.

### 8.6 Quality floor

Responsive to mobile; visible keyboard focus; reduced motion respected; all colour pairs meet WCAG AA; every AI-generated score labelled as such at the point of display.

---

## 9. Phase 2 — sandboxed preview (deferred)

If time allows after the event: teams' uploaded static HTML bundles served live in a sandboxed iframe from a **second Netlify site on a separate origin**, with a strict CSP and a documented takedown path. Origin isolation is non-negotiable; same-origin rendering of participant HTML would expose the main site to stored XSS. Deferred because it is the one genuinely risky piece and is not required for judging.

---

## 10. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| CISC does not approve AI judging before Oct 3 | **High** | §1.1 fallback: advisory mode, participant vote decides. No rework. |
| Participants judged under rules they were not shown | **High** | Update `README.md` and `event-program.md` before the event, not after. |
| A team disputes its ranking | Medium | Committed transcripts (§5.5) plus a CISC-owned appeals path. |
| Netlify Forms tier limits exceeded | Low | Verify submission caps, file-size limits, and Blobs pricing against ~14 teams before build. Open item. |
| Fewer than 4 teams submit | Low | Below 4, the bracket degrades to a ranked list. Detect and switch automatically. |
| Uploaded artifact contains personal data | Medium | Ground rules already forbid it. Admin review before results publish; takedown path documented. |

---

## 11. Timeline

14 days to the event.

| Window | Work |
|---|---|
| Sept 19–21 | Implementation plan. CISC conversation opened on §1.1. Netlify limits verified. |
| Sept 22–26 | Site build: hero, form, gallery. Netlify + Forms wired. Sync Action. |
| Sept 27–30 | Judging: personas, schemas, `run_panel.py`, `bracket.py`, fixtures, mock-LLM tests. |
| Oct 1–2 | Full dry run on fixtures. Bracket page. Accessibility pass. Repo docs updated. |
| **Oct 3** | Event. Sync Action runs live. |
| Oct 4–6 | Submissions close, admin review, judging dispatched, results published. |

---

## 12. Open items

1. **CISC approval of §1.1** — blocks publication of results, not the build.
2. **Netlify tier limits** — submission cap, per-file size limit, Blobs pricing at ~14 teams. Verify before build.
3. **Model choice for the panel** — resolve during planning.
4. **Submission close time** — end of event, or a grace window to the following day?
5. **Who adjudicates appeals** — CISC decision.

# Day in Our Data Showcase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a companion site for the Day in Our Data hackathon that collects team submissions, publishes a showcase, runs a participant vote that decides the awards, and publishes an independent five-persona AI judging panel beside it for comparison.

**Architecture:** A static site on Netlify collects submissions and ballots through Netlify Forms. GitHub Actions jobs sync form data into committed JSON, run the AI panel against the Anthropic API, tally ballots, and compute agreement statistics. The site is two-and-a-half pages of plain HTML reading committed JSON — no framework, no database, no server.

**Tech Stack:** Python 3.11+, `anthropic` SDK 1.x, `pydantic`, `pytest`; plain HTML/CSS/JS; Netlify (hosting + Forms); GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-19-day-in-our-data-showcase-design.md`

## Global Constraints

- **Model:** `claude-opus-5`. Exact string, no date suffix. Configurable via `JUDGE_MODEL` env var.
- **No API spend in CI.** `ci.yml` runs with `ANTHROPIC_API_KEY` unset. Only `judge.yml` (manual dispatch) may call the API.
- **No red in the UI palette.** Tokens are fixed: `--ink #102a56`, `--civic #1559d6`, `--canopy #14503a`, `--leaf #2d7a55`, `--sprout #7fb996`, `--glass #ffc629`, `--paper #eef2ef`, `--rule #c9d3e4`.
- **Ballot codes never enter the repo.** Only the `BALLOT_CODES` Actions secret and printed slips.
- **Judges never see team names in pass 1.** Only `anon_id`.
- **AI decides nothing.** Every surface displaying an AI score labels it AI-generated; the vote decides awards.
- **Prompts state that code is not required.** A dataset, map, chart, or documented question must not be penalised for lacking code.
- **Python 3.11+**, `match`/`case` permitted. Type hints on all public functions.

## Spec amendments discovered while planning

Three gaps found in the spec. Apply these; they are reflected in the tasks below.

1. **§5.3 even-vote matchup tie.** The spec covers all-five-abstain but not a 2–2 split after abstentions. **Rule: any tie, including 0–0, advances the higher seed.** One rule, consistent with the all-abstain case.
2. **§6.3 duplicate picks within one ballot.** Not covered. **Rule: a ballot whose three picks are not distinct is invalid.** Otherwise one voter triples a project's count.
3. **§5.4 cost, and Open Item 1.** The spec priced Sonnet. At `claude-opus-5` ($5/$25 per MTok) with adaptive thinking, expect **~$10–15**, and pass 1 runs through the Batch API at 50%. Still trivial. Open Item 1 is resolved: `claude-opus-5`.

---

### Task 1: Project scaffolding and zero-spend CI

**Files:**
- Create: `pyproject.toml`, `judging/__init__.py`, `voting/__init__.py`, `tests/__init__.py`, `.github/workflows/ci.yml`
- Test: `tests/test_environment.py`

**Interfaces:**
- Consumes: nothing
- Produces: the `judging` and `voting` packages; a green `pytest` run

- [ ] **Step 1: Write the failing test**

```python
# tests/test_environment.py
import os


def test_ci_runs_without_api_credentials():
    """CI must never reach the network. If a key is present, the mock path is not being proven."""
    if os.environ.get("CI") == "true":
        assert not os.environ.get("ANTHROPIC_API_KEY"), (
            "ANTHROPIC_API_KEY is set in CI; the zero-spend guarantee is broken"
        )


def test_packages_import():
    import judging
    import voting

    assert judging is not None
    assert voting is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_environment.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'judging'`

- [ ] **Step 3: Write minimal implementation**

```toml
# pyproject.toml
[project]
name = "day-in-our-data-showcase"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["anthropic>=1.0.0", "pydantic>=2.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.setuptools]
packages = ["judging", "voting"]
```

```python
# judging/__init__.py
"""AI judging panel for Day in Our Data."""
```

```python
# voting/__init__.py
"""Participant ballot handling for Day in Our Data."""
```

```python
# tests/__init__.py
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pip install -e ".[dev]" && python -m pytest tests/ -v`
Expected: PASS, 2 passed

- [ ] **Step 5: Add CI workflow**

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - run: python -m pytest tests/ -v
        env:
          CI: "true"
          # ANTHROPIC_API_KEY deliberately unset - see tests/test_environment.py
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml judging/ voting/ tests/ .github/workflows/ci.yml
git commit -m "chore: scaffold packages and zero-spend CI"
```

---

### Task 2: Submission model and fixtures

**Files:**
- Create: `judging/models.py`, `tests/fixtures/submissions.json`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Submission` (pydantic model, fields per spec §4.1), `Artifact`, `load_submissions(path: Path) -> list[Submission]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from pathlib import Path

from judging.models import Submission, load_submissions

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_all_fixture_submissions():
    subs = load_submissions(FIXTURES / "submissions.json")
    assert len(subs) == 6
    assert all(isinstance(s, Submission) for s in subs)


def test_anon_ids_are_unique():
    subs = load_submissions(FIXTURES / "submissions.json")
    assert len({s.anon_id for s in subs}) == len(subs)


def test_no_code_submission_is_valid():
    """A cleaned dataset with no repo is a first-class submission."""
    subs = load_submissions(FIXTURES / "submissions.json")
    no_code = next(s for s in subs if s.id == "sub_002")
    assert no_code.repo_url is None
    assert no_code.artifacts


def test_large_file_url_is_optional():
    subs = load_submissions(FIXTURES / "submissions.json")
    assert any(s.large_file_url for s in subs)
    assert any(s.large_file_url is None for s in subs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'judging.models'`

- [ ] **Step 3: Write minimal implementation**

```python
# judging/models.py
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class Artifact(BaseModel):
    filename: str
    url: str
    bytes: int


class Submission(BaseModel):
    id: str
    anon_id: str
    team_name: str
    project_title: str
    description: str
    solves_for: str
    starter_project: str
    repo_url: str | None = None
    demo_url: str | None = None
    artifacts: list[Artifact] = []
    large_file_url: str | None = None
    submitted_at: datetime


def load_submissions(path: Path) -> list[Submission]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Submission.model_validate(item) for item in data]
```

- [ ] **Step 4: Create the fixture file**

Six submissions covering the spec's §9 cases. Use this exact content.

```json
[
  {
    "id": "sub_001", "anon_id": "P-01", "team_name": "Bike Lane Brigade",
    "project_title": "Safe Routes Gap Map",
    "description": "A map layering the bike network against school attendance zones and five years of crash records, showing which blocks on a walk-to-school route have no protected infrastructure.",
    "solves_for": "Parents deciding whether their kid can bike to school alone.",
    "starter_project": "04-can-a-kid-bike-to-school-safely",
    "repo_url": "https://github.com/example/safe-routes", "demo_url": "https://example.com/safe-routes",
    "artifacts": [{"filename": "gap-map.png", "url": "https://files.example/gap-map.png", "bytes": 482000}],
    "large_file_url": null, "submitted_at": "2026-10-03T14:31:00Z"
  },
  {
    "id": "sub_002", "anon_id": "P-02", "team_name": "Parcel People",
    "project_title": "Assessment Fairness Dataset",
    "description": "A cleaned, documented dataset of assessed value per square foot for every Oak Park residential parcel, with a data dictionary and a written note on the three joins that were ambiguous.",
    "solves_for": "Anyone who wants to check whether their assessment is in line with comparable homes.",
    "starter_project": "01-is-my-assessment-fair",
    "repo_url": null, "demo_url": null,
    "artifacts": [{"filename": "assessments-clean.csv", "url": "https://files.example/assessments.csv", "bytes": 2100000}],
    "large_file_url": "https://drive.example/full-parcel-export", "submitted_at": "2026-10-03T14:45:00Z"
  },
  {
    "id": "sub_003", "anon_id": "P-03", "team_name": "Canopy Count",
    "project_title": "Urban Forest 10-20-30 Check",
    "description": "A chart testing Oak Park's 18,800 public trees against the 10-20-30 diversity rule, by species, genus, and family, with the three streets most exposed to a single-species loss.",
    "solves_for": "The Forestry division planning replacement planting.",
    "starter_project": "11-how-resilient-is-our-urban-forest",
    "repo_url": "https://github.com/example/canopy", "demo_url": null,
    "artifacts": [{"filename": "diversity.png", "url": "https://files.example/diversity.png", "bytes": 310000}],
    "large_file_url": null, "submitted_at": "2026-10-03T14:50:00Z"
  },
  {
    "id": "sub_004", "anon_id": "P-04", "team_name": "Broken Link Crew",
    "project_title": "Commission Finder",
    "description": "A tool to match a resident interest to one of the eighteen citizen boards and commissions, with meeting schedules and application links.",
    "solves_for": "Residents who want to serve but cannot tell the commissions apart.",
    "starter_project": "13-what-do-our-commissions-do",
    "repo_url": "https://github.com/example/does-not-exist-404", "demo_url": null,
    "artifacts": [], "large_file_url": null, "submitted_at": "2026-10-03T14:55:00Z"
  },
  {
    "id": "sub_005", "anon_id": "P-05", "team_name": "Quiet Submitters",
    "project_title": "Transit Stop Audit",
    "description": "",
    "solves_for": "",
    "starter_project": "06-which-bus-stops-need-help",
    "repo_url": null, "demo_url": null,
    "artifacts": [], "large_file_url": null, "submitted_at": "2026-10-03T14:58:00Z"
  },
  {
    "id": "sub_006", "anon_id": "P-06", "team_name": "ECHO Watchers",
    "project_title": "What ECHO Sees",
    "description": "An aggregate view of the Village's non-police response team call types by month, with a written caution about what the categories do and do not capture.",
    "solves_for": "Residents and trustees evaluating the ECHO program.",
    "starter_project": "15-what-does-echo-see",
    "repo_url": "https://github.com/example/echo", "demo_url": "https://example.com/echo",
    "artifacts": [{"filename": "echo-calls.png", "url": "https://files.example/echo.png", "bytes": 205000}],
    "large_file_url": null, "submitted_at": "2026-10-03T15:02:00Z"
  }
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_models.py -v`
Expected: PASS, 4 passed

- [ ] **Step 6: Commit**

```bash
git add judging/models.py tests/fixtures/submissions.json tests/test_models.py
git commit -m "feat: add submission model and six-case fixture set"
```

---

### Task 3: Bracket engine

**Files:**
- Create: `judging/bracket.py`
- Test: `tests/test_bracket.py`

**Interfaces:**
- Consumes: `judging.models.Submission`
- Produces:
  - `mean_score(scores: dict[str, int]) -> float`
  - `seed_entries(entries: list[SeedEntry]) -> list[SeedEntry]`
  - `bracket_slots(size: int) -> list[int]`
  - `build_rounds(seeded: list[SeedEntry]) -> list[list[Pairing]]`
  - `resolve(votes: list[Vote], a: str, b: str, seed_of: dict[str, int]) -> str`
  - `SeedEntry(anon_id, scores, submitted_at)`, `Pairing(a, b)`, `Vote(persona, winner, swap_confirmed)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bracket.py
from datetime import datetime, timezone

import pytest

from judging.bracket import (
    Pairing, SeedEntry, Vote, bracket_slots, build_rounds, mean_score, resolve, seed_entries,
)

PERSONAS = ["civic-impact", "data-integrity", "usability-access", "craft", "continuation"]


def entry(anon_id: str, scores: list[int], minute: int = 0) -> SeedEntry:
    return SeedEntry(
        anon_id=anon_id,
        scores=dict(zip(PERSONAS, scores)),
        submitted_at=datetime(2026, 10, 3, 14, minute, tzinfo=timezone.utc),
    )


def test_mean_score():
    assert mean_score({"a": 4, "b": 5, "c": 3}) == 4.0


def test_seeding_orders_by_mean_descending():
    ordered = seed_entries([entry("P-01", [3, 3, 3, 3, 3]), entry("P-02", [5, 5, 5, 5, 5])])
    assert [e.anon_id for e in ordered] == ["P-02", "P-01"]


def test_seeding_tie_breaks_on_civic_impact_then_data_integrity():
    # identical means of 3.0; P-02 wins on civic impact
    a = entry("P-01", [2, 4, 3, 3, 3])
    b = entry("P-02", [4, 2, 3, 3, 3])
    assert [e.anon_id for e in seed_entries([a, b])] == ["P-02", "P-01"]


def test_seeding_final_tie_breaks_on_earlier_submission():
    a = entry("P-01", [3, 3, 3, 3, 3], minute=50)
    b = entry("P-02", [3, 3, 3, 3, 3], minute=10)
    assert [e.anon_id for e in seed_entries([a, b])] == ["P-02", "P-01"]


@pytest.mark.parametrize(
    "size,expected",
    [(2, [1, 2]), (4, [1, 4, 2, 3]), (8, [1, 8, 4, 5, 2, 7, 3, 6])],
)
def test_bracket_slots_are_standard_seeding_order(size, expected):
    assert bracket_slots(size) == expected


def test_six_entries_give_top_two_seeds_byes():
    seeded = seed_entries([entry(f"P-0{i}", [6 - i] * 5) for i in range(1, 7)])
    rounds = build_rounds(seeded)
    first = rounds[0]
    byes = [p for p in first if p.b is None]
    assert len(byes) == 2
    assert {p.a for p in byes} == {"P-01", "P-02"}


def test_majority_of_surviving_votes_wins():
    votes = [
        Vote("civic-impact", "P-01", True), Vote("data-integrity", "P-01", True),
        Vote("usability-access", "P-02", True), Vote("craft", "P-02", True),
        Vote("continuation", "P-01", True),
    ]
    assert resolve(votes, "P-01", "P-02", {"P-01": 1, "P-02": 2}) == "P-01"


def test_votes_that_flip_under_swap_do_not_count():
    votes = [
        Vote("civic-impact", "P-02", False), Vote("data-integrity", "P-02", False),
        Vote("usability-access", "P-02", False), Vote("craft", "P-01", True),
        Vote("continuation", "P-01", True),
    ]
    # three unconfirmed votes are discarded; P-01 wins 2-0
    assert resolve(votes, "P-01", "P-02", {"P-01": 1, "P-02": 2}) == "P-01"


def test_all_abstentions_advance_the_higher_seed():
    votes = [Vote(p, "P-02", False) for p in PERSONAS]
    assert resolve(votes, "P-01", "P-02", {"P-01": 1, "P-02": 2}) == "P-01"


def test_even_split_advances_the_higher_seed():
    """Spec amendment 1: a 2-2 tie after abstentions goes to the higher seed."""
    votes = [
        Vote("civic-impact", "P-01", True), Vote("data-integrity", "P-01", True),
        Vote("usability-access", "P-02", True), Vote("craft", "P-02", True),
        Vote("continuation", "P-02", False),
    ]
    assert resolve(votes, "P-01", "P-02", {"P-01": 1, "P-02": 2}) == "P-01"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_bracket.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'judging.bracket'`

- [ ] **Step 3: Write minimal implementation**

```python
# judging/bracket.py
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

CIVIC = "civic-impact"
INTEGRITY = "data-integrity"


@dataclass(frozen=True)
class SeedEntry:
    anon_id: str
    scores: dict[str, int]
    submitted_at: datetime


@dataclass(frozen=True)
class Pairing:
    a: str
    b: str | None  # None means a bye


@dataclass(frozen=True)
class Vote:
    persona: str
    winner: str
    swap_confirmed: bool


def mean_score(scores: dict[str, int]) -> float:
    return sum(scores.values()) / len(scores)


def seed_entries(entries: list[SeedEntry]) -> list[SeedEntry]:
    """Highest mean first. Ties: civic impact, then data integrity, then earliest submission."""
    return sorted(
        entries,
        key=lambda e: (
            -mean_score(e.scores),
            -e.scores[CIVIC],
            -e.scores[INTEGRITY],
            e.submitted_at,
        ),
    )


def bracket_slots(size: int) -> list[int]:
    """Standard tournament seeding order: 1 plays the lowest seed, favourites meet last."""
    slots = [1]
    while len(slots) < size:
        n = len(slots) * 2
        slots = [s for pair in ((x, n + 1 - x) for x in slots) for s in pair]
    return slots


def _bracket_size(n: int) -> int:
    size = 1
    while size < n:
        size *= 2
    return size


def build_rounds(seeded: list[SeedEntry]) -> list[list[Pairing]]:
    """Round one only; later rounds depend on results and are built as they resolve."""
    size = _bracket_size(len(seeded))
    by_seed = {i + 1: e.anon_id for i, e in enumerate(seeded)}
    ordered = [by_seed.get(s) for s in bracket_slots(size)]
    first: list[Pairing] = []
    for i in range(0, size, 2):
        a, b = ordered[i], ordered[i + 1]
        if a is None and b is None:
            continue
        if a is None:
            a, b = b, None
        first.append(Pairing(a=a, b=b))
    return [first]


def resolve(votes: list[Vote], a: str, b: str, seed_of: dict[str, int]) -> str:
    """Majority of votes that survived the position swap. Any tie advances the higher seed."""
    higher = a if seed_of[a] < seed_of[b] else b
    counted = Counter(v.winner for v in votes if v.swap_confirmed)
    if not counted:
        return higher
    top = counted.most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        return higher
    return top[0][0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_bracket.py -v`
Expected: PASS, 11 passed

- [ ] **Step 5: Commit**

```bash
git add judging/bracket.py tests/test_bracket.py
git commit -m "feat: add bracket seeding, byes, and swap-aware majority resolution"
```

---

### Task 4: Rank correlation

**Files:**
- Create: `voting/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: nothing
- Produces: `average_ranks(values: dict[str, float], higher_is_better: bool = True) -> dict[str, float]`, `spearman(a: dict[str, float], b: dict[str, float]) -> float | None`

No SciPy — one function, hand-checkable, and one fewer dependency in a workflow that must stay reproducible.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stats.py
import pytest

from voting.stats import average_ranks, spearman


def test_average_ranks_descending():
    assert average_ranks({"a": 10, "b": 5, "c": 1}) == {"a": 1.0, "b": 2.0, "c": 3.0}


def test_tied_values_share_the_average_rank():
    # two values tied for ranks 1 and 2 both get 1.5
    assert average_ranks({"a": 10, "b": 10, "c": 1}) == {"a": 1.5, "b": 1.5, "c": 3.0}


def test_perfect_agreement_is_one():
    crowd = {"a": 3, "b": 2, "c": 1}
    panel = {"a": 30, "b": 20, "c": 10}
    assert spearman(crowd, panel) == pytest.approx(1.0)


def test_perfect_disagreement_is_minus_one():
    crowd = {"a": 3, "b": 2, "c": 1}
    panel = {"a": 10, "b": 20, "c": 30}
    assert spearman(crowd, panel) == pytest.approx(-1.0)


def test_known_value():
    # ranks a..e = 1..5 vs 2,1,4,3,5 -> d^2 sum = 1+1+1+1+0 = 4
    # rho = 1 - (6*4) / (5 * 24) = 1 - 24/120 = 0.8
    crowd = {"a": 50, "b": 40, "c": 30, "d": 20, "e": 10}
    panel = {"a": 40, "b": 50, "c": 20, "d": 30, "e": 10}
    assert spearman(crowd, panel) == pytest.approx(0.8)


def test_returns_none_when_a_side_has_no_variance():
    """All-tied input has zero standard deviation; correlation is undefined, not zero."""
    assert spearman({"a": 1, "b": 1}, {"a": 2, "b": 1}) is None


def test_returns_none_below_two_items():
    assert spearman({"a": 1}, {"a": 1}) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_stats.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'voting.stats'`

- [ ] **Step 3: Write minimal implementation**

```python
# voting/stats.py
from __future__ import annotations

from math import sqrt


def average_ranks(values: dict[str, float], higher_is_better: bool = True) -> dict[str, float]:
    """Rank 1 is best. Tied values share the average of the ranks they span."""
    items = sorted(values.items(), key=lambda kv: -kv[1] if higher_is_better else kv[1])
    ranks: dict[str, float] = {}
    i = 0
    while i < len(items):
        j = i
        while j + 1 < len(items) and items[j + 1][1] == items[i][1]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[items[k][0]] = shared
        i = j + 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sqrt(sum((x - mx) ** 2 for x in xs))
    vy = sqrt(sum((y - my) ** 2 for y in ys))
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy)


def spearman(a: dict[str, float], b: dict[str, float]) -> float | None:
    """Pearson correlation on average ranks, so ties are handled correctly."""
    keys = sorted(set(a) & set(b))
    if len(keys) < 2:
        return None
    ra, rb = average_ranks(a), average_ranks(b)
    return _pearson([ra[k] for k in keys], [rb[k] for k in keys])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_stats.py -v`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add voting/stats.py tests/test_stats.py
git commit -m "feat: add tie-aware rank correlation"
```

---

### Task 5: Ballot validation and tally

**Files:**
- Create: `voting/tally.py`
- Test: `tests/test_tally.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Ballot(code, picks, cast_at)`, `TallyResult(counts, valid, invalid, indicative)`, `tally(ballots, valid_codes, known_ids, floor=10) -> TallyResult`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tally.py
from datetime import datetime, timezone

from voting.tally import Ballot, tally

KNOWN = {"sub_001", "sub_002", "sub_003", "sub_004"}
CODES = {f"CODE{i:03d}" for i in range(1, 21)}


def ballot(code: str, picks: list[str], minute: int = 0) -> Ballot:
    return Ballot(
        code=code, picks=picks,
        cast_at=datetime(2026, 10, 5, 12, minute, tzinfo=timezone.utc),
    )


def valid_set(n: int) -> list[Ballot]:
    return [ballot(f"CODE{i:03d}", ["sub_001", "sub_002", "sub_003"], i) for i in range(1, n + 1)]


def test_counts_each_pick_once_per_ballot():
    result = tally(valid_set(10), CODES, KNOWN)
    assert result.counts["sub_001"] == 10
    assert result.counts["sub_004"] == 0
    assert result.valid == 10


def test_unknown_code_is_invalid():
    result = tally(valid_set(10) + [ballot("NOTACODE", ["sub_001", "sub_002", "sub_003"], 30)], CODES, KNOWN)
    assert result.valid == 10
    assert result.invalid == 1


def test_reused_code_keeps_only_the_first_ballot():
    ballots = valid_set(10) + [ballot("CODE001", ["sub_004", "sub_002", "sub_003"], 40)]
    result = tally(ballots, CODES, KNOWN)
    assert result.valid == 10
    assert result.counts["sub_004"] == 0


def test_unknown_project_invalidates_the_whole_ballot():
    ballots = valid_set(10) + [ballot("CODE011", ["sub_001", "sub_999", "sub_003"], 50)]
    result = tally(ballots, CODES, KNOWN)
    assert result.valid == 10
    assert result.invalid == 1


def test_duplicate_picks_invalidate_the_ballot():
    """Spec amendment 2: three picks must be distinct, or one voter triples a count."""
    ballots = valid_set(10) + [ballot("CODE011", ["sub_001", "sub_001", "sub_002"], 55)]
    result = tally(ballots, CODES, KNOWN)
    assert result.valid == 10
    assert result.invalid == 1
    assert result.counts["sub_001"] == 10


def test_below_floor_turnout_is_marked_indicative():
    result = tally(valid_set(9), CODES, KNOWN)
    assert result.indicative is True


def test_at_floor_turnout_is_not_indicative():
    result = tally(valid_set(10), CODES, KNOWN)
    assert result.indicative is False


def test_codes_are_absent_from_the_result():
    result = tally(valid_set(10), CODES, KNOWN)
    assert "CODE001" not in repr(result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tally.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'voting.tally'`

- [ ] **Step 3: Write minimal implementation**

```python
# voting/tally.py
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime

TURNOUT_FLOOR = 10
PICKS_PER_BALLOT = 3


@dataclass(frozen=True)
class Ballot:
    code: str
    picks: list[str]
    cast_at: datetime


@dataclass
class TallyResult:
    counts: dict[str, int]
    valid: int
    invalid: int
    indicative: bool
    _codes_never_stored: None = field(default=None, repr=False)


def tally(
    ballots: list[Ballot],
    valid_codes: set[str],
    known_ids: set[str],
    floor: int = TURNOUT_FLOOR,
) -> TallyResult:
    counts: Counter[str] = Counter({pid: 0 for pid in known_ids})
    seen: set[str] = set()
    valid = invalid = 0

    for b in sorted(ballots, key=lambda x: x.cast_at):
        if b.code not in valid_codes or b.code in seen:
            invalid += 1
            continue
        if len(b.picks) != PICKS_PER_BALLOT or len(set(b.picks)) != PICKS_PER_BALLOT:
            invalid += 1
            continue
        if any(p not in known_ids for p in b.picks):
            invalid += 1
            continue
        seen.add(b.code)
        counts.update(b.picks)
        valid += 1

    return TallyResult(
        counts=dict(counts), valid=valid, invalid=invalid, indicative=valid < floor
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_tally.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add voting/tally.py tests/test_tally.py
git commit -m "feat: add ballot validation, tally, and turnout floor"
```

---

### Task 6: Judge client with mock and real backends

**Files:**
- Create: `judging/schemas.py`, `judging/client.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `ScoreOutput` / `MatchupOutput` (pydantic)
  - `JudgeClient` protocol with `score(system, user) -> ScoreOutput | None` and `compare(system, user) -> MatchupOutput | None`
  - `MockJudgeClient(responses: list)`, `AnthropicJudgeClient(model=...)`
  - Both return `None` on refusal or validation failure after one retry — the abstention path

- [ ] **Step 1: Write the failing test**

```python
# tests/test_client.py
from judging.client import MockJudgeClient
from judging.schemas import MatchupOutput, ScoreOutput


def test_mock_returns_queued_score():
    c = MockJudgeClient([ScoreOutput(score=4, justification="Clear civic use.", evidence=["README"])])
    out = c.score("sys", "user")
    assert out.score == 4


def test_mock_returns_none_for_queued_abstention():
    c = MockJudgeClient([None])
    assert c.score("sys", "user") is None


def test_score_rejects_empty_evidence():
    """A verdict with no evidence is not a verdict."""
    import pydantic, pytest

    with pytest.raises(pydantic.ValidationError):
        ScoreOutput(score=4, justification="Looks good.", evidence=[])


def test_score_rejects_out_of_range():
    import pydantic, pytest

    with pytest.raises(pydantic.ValidationError):
        ScoreOutput(score=6, justification="x", evidence=["y"])


def test_matchup_records_winner_and_reasoning():
    m = MatchupOutput(winner="A", reasoning="A cites its sources; B does not.")
    assert m.winner == "A"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'judging.client'`

- [ ] **Step 3: Write the schemas**

```python
# judging/schemas.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ScoreOutput(BaseModel):
    score: int = Field(ge=1, le=5)
    justification: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)


class MatchupOutput(BaseModel):
    winner: Literal["A", "B"]
    reasoning: str = Field(min_length=1)
```

- [ ] **Step 4: Write the clients**

`messages.parse()` validates against the pydantic model server-side and returns `parsed_output`, so schema enforcement and the retry-then-abstain path are the same code. A `refusal` stop reason is treated as an abstention rather than an error.

```python
# judging/client.py
from __future__ import annotations

import os
from typing import Protocol

from judging.schemas import MatchupOutput, ScoreOutput

DEFAULT_MODEL = os.environ.get("JUDGE_MODEL", "claude-opus-5")
MAX_TOKENS = 16000


class JudgeClient(Protocol):
    def score(self, system: str, user: str) -> ScoreOutput | None: ...
    def compare(self, system: str, user: str) -> MatchupOutput | None: ...


class MockJudgeClient:
    """Returns queued responses in order. Used by every test; never touches the network."""

    def __init__(self, responses: list[ScoreOutput | MatchupOutput | None]):
        self._queue = list(responses)
        self.calls: list[tuple[str, str]] = []

    def _next(self, system: str, user: str):
        self.calls.append((system, user))
        return self._queue.pop(0) if self._queue else None

    def score(self, system: str, user: str) -> ScoreOutput | None:
        return self._next(system, user)

    def compare(self, system: str, user: str) -> MatchupOutput | None:
        return self._next(system, user)


class AnthropicJudgeClient:
    """Real backend. One retry on validation failure, then abstain."""

    def __init__(self, model: str = DEFAULT_MODEL):
        import anthropic

        self._client = anthropic.Anthropic()
        self._model = model

    def _parse(self, system: str, user: str, output_format):
        for _ in range(2):
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=output_format,
            )
            if response.stop_reason == "refusal":
                return None
            parsed = getattr(response, "parsed_output", None)
            if parsed is not None:
                return parsed
        return None

    def score(self, system: str, user: str) -> ScoreOutput | None:
        return self._parse(system, user, ScoreOutput)

    def compare(self, system: str, user: str) -> MatchupOutput | None:
        return self._parse(system, user, MatchupOutput)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_client.py -v`
Expected: PASS, 5 passed

- [ ] **Step 6: Commit**

```bash
git add judging/schemas.py judging/client.py tests/test_client.py
git commit -m "feat: add judge client protocol with mock and Anthropic backends"
```

---

### Task 7: Persona prompts and evidence assembly

**Files:**
- Create: `judging/personas/civic-impact.md`, `data-integrity.md`, `usability-access.md`, `craft.md`, `continuation.md`, `judging/rubric.md`, `judging/prompts.py`
- Test: `tests/test_prompts.py`

**Interfaces:**
- Consumes: `judging.models.Submission`
- Produces: `PERSONAS: list[str]`, `load_persona(name) -> str`, `evidence_block(sub, repo_readme=None) -> str`, `matchup_user(a_block, b_block) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prompts.py
from pathlib import Path

from judging.models import load_submissions
from judging.prompts import PERSONAS, evidence_block, load_persona, matchup_user

FIXTURES = Path(__file__).parent / "fixtures"


def test_five_personas_exist():
    assert len(PERSONAS) == 5


def test_every_persona_states_code_is_not_required():
    for name in PERSONAS:
        text = load_persona(name).lower()
        assert "code is not required" in text, f"{name} may penalise non-coders"


def test_every_persona_demands_evidence():
    for name in PERSONAS:
        assert "evidence" in load_persona(name).lower()


def test_evidence_block_never_contains_the_team_name():
    sub = next(s for s in load_submissions(FIXTURES / "submissions.json") if s.id == "sub_001")
    block = evidence_block(sub)
    assert sub.team_name not in block
    assert sub.anon_id in block


def test_evidence_block_marks_missing_material():
    sub = next(s for s in load_submissions(FIXTURES / "submissions.json") if s.id == "sub_005")
    block = evidence_block(sub)
    assert "(not provided)" in block


def test_matchup_user_labels_sides_a_and_b():
    text = matchup_user("ALPHA", "BETA")
    assert "Submission A" in text and "Submission B" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_prompts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'judging.prompts'`

- [ ] **Step 3: Write the five persona files**

Each follows this shape. Write `judging/personas/civic-impact.md` exactly as below, then the other four with the same structure, substituting the role paragraph and the scale.

```markdown
<!-- judging/personas/civic-impact.md -->
You are the Civic Impact judge for Day in Our Data, a one-day civic data
hackathon run by the Village of Oak Park's Civic Information Systems Commission.

Your question: **does this project answer a question a real Oak Park resident
actually has?**

Judge the civic value of the work, not its technical sophistication.
**Code is not required.** A cleaned dataset, a printed map, a chart, or a
clearly documented open question can each score full marks. A project with no
repository is not thereby weaker. Teams had four hours, and many participants
had never written a line of code.

Score 1 to 5:

- **5** — Answers a question residents ask out loud, for a clearly named group of people.
- **4** — Clear civic value; the audience is implied rather than named.
- **3** — Plausibly useful, but the need is assumed rather than shown.
- **2** — Interesting as data work; the civic question is thin.
- **1** — No discernible resident-facing question.

You must ground your score in **evidence**: short quotes or specific pointers
drawn from the material you were given. Never cite anything you were not shown.
If the material is thin, say so, score accordingly, and cite the absence.

Keep the justification to at most two sentences.
```

The other four, same structure, with these questions and scales:

- `data-integrity.md` — "Are sources named and are the limits of the data stated?" 5: sources named and caveats stated unprompted. 1: conclusions with no stated source.
- `usability-access.md` — "Could a resident who is not technical actually use this?" 5: usable at a glance, plain language. 1: requires expertise the audience lacks.
- `craft.md` — "Is it finished and working, in whatever form it takes?" Include: *"A finished CSV outranks a broken web app."* 5: complete and functioning. 1: fragmentary.
- `continuation.md` — "Could CISC or Village staff pick this up on Monday?" 5: documented well enough to hand over. 1: nothing to continue from.

- [ ] **Step 4: Write `judging/rubric.md`**

A public, human-readable page stating the five personas, their questions, the 1–5 scales, and this paragraph verbatim:

```markdown
These scores are generated by a language model panel. **They decide nothing.**
Awards at Day in Our Data are determined by the participant vote. The panel
runs independently so its ranking can be compared against the crowd's — the
comparison is the point, not the verdict.
```

- [ ] **Step 5: Write `judging/prompts.py`**

```python
# judging/prompts.py
from __future__ import annotations

from pathlib import Path

from judging.models import Submission

PERSONAS = ["civic-impact", "data-integrity", "usability-access", "craft", "continuation"]
_DIR = Path(__file__).parent / "personas"


def load_persona(name: str) -> str:
    return (_DIR / f"{name}.md").read_text(encoding="utf-8")


def _or_missing(value: str | None) -> str:
    return value if value else "(not provided)"


def evidence_block(sub: Submission, repo_readme: str | None = None) -> str:
    """Everything a judge sees. Team name deliberately excluded - pass 1 is blind."""
    artifacts = "\n".join(f"  - {a.filename} ({a.bytes} bytes)" for a in sub.artifacts) or "  (none)"
    readme = repo_readme.strip() if repo_readme else "(repository unavailable or not provided)"
    return "\n".join([
        f"Submission {sub.anon_id}",
        f"Title: {_or_missing(sub.project_title)}",
        f"Starter project: {sub.starter_project}",
        "",
        "Description:",
        _or_missing(sub.description),
        "",
        "What it solves for:",
        _or_missing(sub.solves_for),
        "",
        f"Repository: {_or_missing(sub.repo_url)}",
        f"Live demo: {_or_missing(sub.demo_url)}",
        "Artifacts:",
        artifacts,
        "",
        "Repository README:",
        readme,
    ])


def matchup_user(a_block: str, b_block: str) -> str:
    return "\n".join([
        "Two submissions. Decide which better answers your question.",
        "Answer with winner \"A\" or \"B\" and your reasoning.",
        "",
        "--- Submission A ---", a_block, "",
        "--- Submission B ---", b_block,
    ])
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest tests/test_prompts.py -v`
Expected: PASS, 6 passed

- [ ] **Step 7: Commit**

```bash
git add judging/personas/ judging/rubric.md judging/prompts.py tests/test_prompts.py
git commit -m "feat: add five code-neutral persona prompts and blind evidence assembly"
```

---

### Task 8: Pass 1 — blind scoring

**Files:**
- Create: `judging/pass1.py`
- Test: `tests/test_pass1.py`

**Interfaces:**
- Consumes: `JudgeClient`, `Submission`, `PERSONAS`, `evidence_block`
- Produces: `score_all(client, submissions, readmes=None) -> dict[str, dict[str, int]]` mapping `anon_id -> persona -> score`, and `abstentions: list[tuple[str, str]]`; returns `Pass1Result(scores, abstentions)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pass1.py
from pathlib import Path

from judging.client import MockJudgeClient
from judging.models import load_submissions
from judging.pass1 import score_all
from judging.schemas import ScoreOutput

FIXTURES = Path(__file__).parent / "fixtures"


def ok(n: int) -> ScoreOutput:
    return ScoreOutput(score=n, justification="Grounded.", evidence=["description"])


def test_scores_every_submission_with_every_persona():
    subs = load_submissions(FIXTURES / "submissions.json")
    client = MockJudgeClient([ok(4)] * (len(subs) * 5))
    result = score_all(client, subs)
    assert len(result.scores) == len(subs)
    assert all(len(p) == 5 for p in result.scores.values())


def test_abstention_is_recorded_and_excluded():
    subs = load_submissions(FIXTURES / "submissions.json")[:1]
    client = MockJudgeClient([ok(4), None, ok(3), ok(3), ok(3)])
    result = score_all(client, subs)
    assert len(result.abstentions) == 1
    assert len(result.scores["P-01"]) == 4


def test_judges_never_receive_the_team_name():
    subs = load_submissions(FIXTURES / "submissions.json")
    client = MockJudgeClient([ok(4)] * (len(subs) * 5))
    score_all(client, subs)
    sent = " ".join(user for _, user in client.calls)
    for s in subs:
        assert s.team_name not in sent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pass1.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'judging.pass1'`

- [ ] **Step 3: Write minimal implementation**

```python
# judging/pass1.py
from __future__ import annotations

from dataclasses import dataclass

from judging.client import JudgeClient
from judging.models import Submission
from judging.prompts import PERSONAS, evidence_block, load_persona


@dataclass
class Pass1Result:
    scores: dict[str, dict[str, int]]
    abstentions: list[tuple[str, str]]
    justifications: dict[str, dict[str, str]]


def score_all(
    client: JudgeClient,
    submissions: list[Submission],
    readmes: dict[str, str] | None = None,
) -> Pass1Result:
    readmes = readmes or {}
    scores: dict[str, dict[str, int]] = {}
    justifications: dict[str, dict[str, str]] = {}
    abstentions: list[tuple[str, str]] = []

    for sub in submissions:
        block = evidence_block(sub, readmes.get(sub.id))
        scores[sub.anon_id] = {}
        justifications[sub.anon_id] = {}
        for persona in PERSONAS:
            out = client.score(load_persona(persona), block)
            if out is None:
                abstentions.append((sub.anon_id, persona))
                continue
            scores[sub.anon_id][persona] = out.score
            justifications[sub.anon_id][persona] = out.justification

    return Pass1Result(scores=scores, abstentions=abstentions, justifications=justifications)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pass1.py -v`
Expected: PASS, 3 passed

- [ ] **Step 5: Commit**

```bash
git add judging/pass1.py tests/test_pass1.py
git commit -m "feat: add blind pass-1 scoring with abstention tracking"
```

---

### Task 9: Pass 2 — position-swapped matchups

**Files:**
- Create: `judging/pass2.py`
- Test: `tests/test_pass2.py`

**Interfaces:**
- Consumes: `JudgeClient`, `Pairing`, `evidence_block`, `resolve`
- Produces: `judge_matchup(client, a_sub, b_sub, seed_of) -> MatchupRecord`, `MatchupRecord(a, b, winner, votes)`

Each persona votes twice — once with the real submission as A, once swapped. A vote counts only if both orderings name the same submission.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pass2.py
from pathlib import Path

from judging.client import MockJudgeClient
from judging.models import load_submissions
from judging.pass2 import judge_matchup
from judging.schemas import MatchupOutput

FIXTURES = Path(__file__).parent / "fixtures"
SEEDS = {"P-01": 1, "P-02": 2}


def pick(side: str) -> MatchupOutput:
    return MatchupOutput(winner=side, reasoning="Because of the cited evidence.")


def two_subs():
    subs = load_submissions(FIXTURES / "submissions.json")
    return subs[0], subs[1]


def test_consistent_judge_vote_is_confirmed():
    a, b = two_subs()
    # normal order: A wins. swapped order: B wins (B is now the original A).
    client = MockJudgeClient([pick("A"), pick("B")] * 5)
    record = judge_matchup(client, a, b, SEEDS)
    assert all(v.swap_confirmed for v in record.votes)
    assert record.winner == "P-01"


def test_position_biased_judge_is_not_counted():
    a, b = two_subs()
    # always picks whatever is in slot A - the classic position bias
    client = MockJudgeClient([pick("A"), pick("A")] * 5)
    record = judge_matchup(client, a, b, SEEDS)
    assert not any(v.swap_confirmed for v in record.votes)
    assert record.winner == "P-01"  # all abstained -> higher seed


def test_refusal_in_either_direction_abstains():
    a, b = two_subs()
    client = MockJudgeClient([pick("A"), None] * 5)
    record = judge_matchup(client, a, b, SEEDS)
    assert not any(v.swap_confirmed for v in record.votes)


def test_each_persona_is_called_twice():
    a, b = two_subs()
    client = MockJudgeClient([pick("A"), pick("B")] * 5)
    judge_matchup(client, a, b, SEEDS)
    assert len(client.calls) == 10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pass2.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'judging.pass2'`

- [ ] **Step 3: Write minimal implementation**

```python
# judging/pass2.py
from __future__ import annotations

from dataclasses import dataclass

from judging.bracket import Vote, resolve
from judging.client import JudgeClient
from judging.models import Submission
from judging.prompts import PERSONAS, evidence_block, load_persona, matchup_user


@dataclass
class MatchupRecord:
    a: str
    b: str
    winner: str
    votes: list[Vote]
    reasoning: dict[str, str]


def judge_matchup(
    client: JudgeClient,
    a_sub: Submission,
    b_sub: Submission,
    seed_of: dict[str, int],
    readmes: dict[str, str] | None = None,
) -> MatchupRecord:
    readmes = readmes or {}
    a_block = evidence_block(a_sub, readmes.get(a_sub.id))
    b_block = evidence_block(b_sub, readmes.get(b_sub.id))

    votes: list[Vote] = []
    reasoning: dict[str, str] = {}

    for persona in PERSONAS:
        system = load_persona(persona)
        first = client.compare(system, matchup_user(a_block, b_block))
        second = client.compare(system, matchup_user(b_block, a_block))

        if first is None or second is None:
            votes.append(Vote(persona, a_sub.anon_id, swap_confirmed=False))
            continue

        # In the swapped call, "A" means b_sub.
        forward = a_sub.anon_id if first.winner == "A" else b_sub.anon_id
        backward = b_sub.anon_id if second.winner == "A" else a_sub.anon_id
        confirmed = forward == backward
        votes.append(Vote(persona, forward, swap_confirmed=confirmed))
        if confirmed:
            reasoning[persona] = first.reasoning

    winner = resolve(votes, a_sub.anon_id, b_sub.anon_id, seed_of)
    return MatchupRecord(
        a=a_sub.anon_id, b=b_sub.anon_id, winner=winner, votes=votes, reasoning=reasoning
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_pass2.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Commit**

```bash
git add judging/pass2.py tests/test_pass2.py
git commit -m "feat: add position-swapped matchup judging"
```

---

### Task 10: Panel runner CLI and transcripts

**Files:**
- Create: `judging/run_panel.py`
- Test: `tests/test_run_panel.py`

**Interfaces:**
- Consumes: everything above
- Produces: `run(submissions, client, out_dir) -> None` writing `scores.json`, `bracket.json`, `transcripts/`; CLI entry `python -m judging.run_panel --submissions PATH --out DIR [--mock]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_run_panel.py
import json
from pathlib import Path

from judging.client import MockJudgeClient
from judging.models import load_submissions
from judging.run_panel import run
from judging.schemas import MatchupOutput, ScoreOutput

FIXTURES = Path(__file__).parent / "fixtures"


def responses(n_subs: int) -> list:
    out = [ScoreOutput(score=4, justification="Grounded.", evidence=["description"])] * (n_subs * 5)
    out += [MatchupOutput(winner=w, reasoning="Cited.") for _ in range(200) for w in ("A", "B")]
    return out


def test_writes_scores_and_bracket(tmp_path: Path):
    subs = load_submissions(FIXTURES / "submissions.json")
    run(subs, MockJudgeClient(responses(len(subs))), tmp_path)
    assert (tmp_path / "scores.json").exists()
    assert (tmp_path / "bracket.json").exists()


def test_bracket_names_a_single_champion(tmp_path: Path):
    subs = load_submissions(FIXTURES / "submissions.json")
    run(subs, MockJudgeClient(responses(len(subs))), tmp_path)
    bracket = json.loads((tmp_path / "bracket.json").read_text())
    assert bracket["champion"] in {s.anon_id for s in subs}


def test_transcripts_are_written_for_every_submission(tmp_path: Path):
    subs = load_submissions(FIXTURES / "submissions.json")
    run(subs, MockJudgeClient(responses(len(subs))), tmp_path)
    files = list((tmp_path / "transcripts").glob("*.json"))
    assert len(files) >= len(subs)


def test_fewer_than_four_submissions_degrades_to_a_ranked_list(tmp_path: Path):
    subs = load_submissions(FIXTURES / "submissions.json")[:3]
    run(subs, MockJudgeClient(responses(3)), tmp_path)
    bracket = json.loads((tmp_path / "bracket.json").read_text())
    assert bracket["mode"] == "ranked_list"
    assert len(bracket["ranking"]) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_run_panel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'judging.run_panel'`

- [ ] **Step 3: Write minimal implementation**

```python
# judging/run_panel.py
from __future__ import annotations

import argparse
import json
from pathlib import Path

from judging.bracket import SeedEntry, build_rounds, mean_score, seed_entries
from judging.client import JudgeClient, MockJudgeClient
from judging.models import Submission, load_submissions
from judging.pass1 import score_all
from judging.pass2 import judge_matchup

MIN_BRACKET = 4


def _write(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def run(submissions: list[Submission], client: JudgeClient, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    (out_dir / "transcripts").mkdir(parents=True, exist_ok=True)

    pass1 = score_all(client, submissions)
    by_anon = {s.anon_id: s for s in submissions}

    _write(out_dir / "scores.json", {
        "model_generated": True,
        "scores": pass1.scores,
        "justifications": pass1.justifications,
        "abstentions": pass1.abstentions,
        "means": {a: mean_score(p) for a, p in pass1.scores.items() if p},
    })
    for anon, personas in pass1.justifications.items():
        _write(out_dir / "transcripts" / f"score-{anon}.json", personas)

    entries = [
        SeedEntry(anon_id=s.anon_id, scores=pass1.scores[s.anon_id], submitted_at=s.submitted_at)
        for s in submissions if len(pass1.scores.get(s.anon_id, {})) == 5
    ]
    seeded = seed_entries(entries)
    seed_of = {e.anon_id: i + 1 for i, e in enumerate(seeded)}
    ranking = [e.anon_id for e in seeded]

    if len(seeded) < MIN_BRACKET:
        _write(out_dir / "bracket.json", {
            "model_generated": True, "mode": "ranked_list",
            "ranking": ranking, "champion": ranking[0] if ranking else None, "rounds": [],
        })
        return

    rounds_out: list[list[dict]] = []
    current = build_rounds(seeded)[0]
    round_no = 1

    while True:
        played: list[dict] = []
        advancing: list[str] = []
        for pair in current:
            if pair.b is None:
                played.append({"a": pair.a, "b": None, "winner": pair.a, "bye": True})
                advancing.append(pair.a)
                continue
            record = judge_matchup(client, by_anon[pair.a], by_anon[pair.b], seed_of)
            played.append({
                "a": record.a, "b": record.b, "winner": record.winner, "bye": False,
                "votes": [
                    {"persona": v.persona, "winner": v.winner, "swap_confirmed": v.swap_confirmed}
                    for v in record.votes
                ],
                "reasoning": record.reasoning,
            })
            advancing.append(record.winner)
        rounds_out.append(played)
        _write(out_dir / "transcripts" / f"round-{round_no}.json", played)

        if len(advancing) <= 1:
            break
        current = [
            type(current[0])(a=advancing[i], b=advancing[i + 1])
            for i in range(0, len(advancing) - 1, 2)
        ]
        round_no += 1

    _write(out_dir / "bracket.json", {
        "model_generated": True, "mode": "bracket", "ranking": ranking,
        "seeds": seed_of, "rounds": rounds_out, "champion": advancing[0],
    })


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Day in Our Data AI judging panel.")
    parser.add_argument("--submissions", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--mock", action="store_true", help="Dry run; makes no API calls.")
    args = parser.parse_args()

    submissions = load_submissions(args.submissions)
    if args.mock:
        from judging.schemas import MatchupOutput, ScoreOutput
        canned = [ScoreOutput(score=3, justification="Mock.", evidence=["mock"])] * 1000
        canned += [MatchupOutput(winner="A", reasoning="Mock.")] * 1000
        client: JudgeClient = MockJudgeClient(canned)
    else:
        from judging.client import AnthropicJudgeClient
        client = AnthropicJudgeClient()

    run(submissions, client, args.out)
    print(f"Wrote results to {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_run_panel.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Verify the full-suite dry run makes no network calls**

Run: `python -m judging.run_panel --submissions tests/fixtures/submissions.json --out /tmp/dryrun --mock`
Expected: `Wrote results to /tmp/dryrun`, exit 0, no credentials required

- [ ] **Step 6: Commit**

```bash
git add judging/run_panel.py tests/test_run_panel.py
git commit -m "feat: add panel runner with transcripts and ranked-list fallback"
```

---

### Task 11: Ballot code generation and the comparison builder

**Files:**
- Create: `voting/generate_codes.py`, `voting/compare.py`
- Test: `tests/test_compare.py`

**Interfaces:**
- Consumes: `voting.stats.spearman`, `voting.tally.TallyResult`
- Produces: `generate_codes(n, rng=None) -> list[str]`, `build_comparison(tally_result, scores, bracket_ranking, id_of) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_compare.py
from voting.compare import build_comparison
from voting.generate_codes import generate_codes
from voting.tally import TallyResult


def test_codes_are_unique_and_long_enough_to_resist_guessing():
    codes = generate_codes(40)
    assert len(set(codes)) == 40
    assert all(len(c) >= 10 for c in codes)


def test_comparison_reports_both_rankings_and_agreement():
    result = TallyResult(
        counts={"sub_001": 9, "sub_002": 6, "sub_003": 3}, valid=12, invalid=0, indicative=False
    )
    scores = {"P-01": {"a": 5}, "P-02": {"a": 4}, "P-03": {"a": 3}}
    id_of = {"P-01": "sub_001", "P-02": "sub_002", "P-03": "sub_003"}
    out = build_comparison(result, scores, ["P-01", "P-02", "P-03"], id_of)
    assert out["crowd_ranking"] == ["sub_001", "sub_002", "sub_003"]
    assert out["spearman"] == 1.0
    assert out["indicative"] is False


def test_indicative_turnout_is_flagged_and_correlation_caveated():
    result = TallyResult(counts={"sub_001": 2, "sub_002": 1}, valid=3, invalid=0, indicative=True)
    out = build_comparison(
        result, {"P-01": {"a": 5}, "P-02": {"a": 4}}, ["P-01", "P-02"],
        {"P-01": "sub_001", "P-02": "sub_002"},
    )
    assert out["indicative"] is True
    assert out["caveat"]


def test_per_persona_agreement_is_reported():
    result = TallyResult(
        counts={"sub_001": 9, "sub_002": 6, "sub_003": 3}, valid=12, invalid=0, indicative=False
    )
    scores = {
        "P-01": {"civic-impact": 5, "craft": 1},
        "P-02": {"civic-impact": 4, "craft": 3},
        "P-03": {"civic-impact": 3, "craft": 5},
    }
    id_of = {"P-01": "sub_001", "P-02": "sub_002", "P-03": "sub_003"}
    out = build_comparison(result, scores, ["P-01", "P-02", "P-03"], id_of)
    assert out["per_persona"]["civic-impact"] == 1.0
    assert out["per_persona"]["craft"] == -1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_compare.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'voting.compare'`

- [ ] **Step 3: Write the code generator**

```python
# voting/generate_codes.py
"""Offline. Prints slips for check-in and the value for the BALLOT_CODES secret.

The generated list must never be committed. The repository is public.
"""
from __future__ import annotations

import argparse
import secrets

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I, O, 0, 1 - these get misread on paper
LENGTH = 10


def generate_codes(n: int, rng: secrets.SystemRandom | None = None) -> list[str]:
    rng = rng or secrets.SystemRandom()
    codes: set[str] = set()
    while len(codes) < n:
        codes.add("".join(rng.choice(ALPHABET) for _ in range(LENGTH)))
    return sorted(codes)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate ballot codes for check-in.")
    parser.add_argument("--count", type=int, default=60)
    args = parser.parse_args()
    codes = generate_codes(args.count)
    print("--- slips (one per attendee) ---")
    for c in codes:
        print(f"  {c}")
    print("\n--- BALLOT_CODES secret value (paste into GitHub Actions secrets) ---")
    print(",".join(codes))
    print("\nDo not commit this output.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write the comparison builder**

```python
# voting/compare.py
from __future__ import annotations

from voting.stats import spearman
from voting.tally import TallyResult

CAVEAT = (
    "Fewer than 10 valid ballots were cast. The crowd ranking is indicative only "
    "and the correlation below should not be read as a result."
)


def _panel_means(scores: dict[str, dict[str, int]]) -> dict[str, float]:
    return {a: sum(p.values()) / len(p) for a, p in scores.items() if p}


def build_comparison(
    result: TallyResult,
    scores: dict[str, dict[str, int]],
    bracket_ranking: list[str],
    id_of: dict[str, str],
) -> dict:
    """Crowd ranking beside the panel's, with agreement statistics. Keyed by submission id."""
    crowd = {sid: n for sid, n in result.counts.items()}
    crowd_ranking = sorted(crowd, key=lambda s: (-crowd[s], s))

    panel_by_id = {id_of[a]: m for a, m in _panel_means(scores).items() if a in id_of}
    shared = {s: crowd[s] for s in crowd if s in panel_by_id}

    personas = sorted({p for per in scores.values() for p in per})
    per_persona: dict[str, float | None] = {}
    for persona in personas:
        vals = {
            id_of[a]: per[persona]
            for a, per in scores.items()
            if persona in per and a in id_of
        }
        per_persona[persona] = spearman(shared, vals)

    return {
        "model_generated_panel": True,
        "awards_determined_by": "participant vote",
        "crowd_ranking": crowd_ranking,
        "crowd_counts": crowd,
        "panel_ranking": [id_of[a] for a in bracket_ranking if a in id_of],
        "panel_means": panel_by_id,
        "spearman": spearman(shared, panel_by_id),
        "per_persona": per_persona,
        "n": result.valid,
        "invalid_ballots": result.invalid,
        "indicative": result.indicative,
        "caveat": CAVEAT if result.indicative else "",
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_compare.py -v`
Expected: PASS, 4 passed

- [ ] **Step 6: Commit**

```bash
git add voting/generate_codes.py voting/compare.py tests/test_compare.py
git commit -m "feat: add ballot code generation and crowd-vs-panel comparison"
```

---

### Task 12: Design tokens and the logo

**Files:**
- Create: `site/styles/tokens.css`, `site/styles/base.css`, `site/assets/logo.svg`
- Test: manual — open `site/index.html` in Task 13

**Interfaces:**
- Consumes: upstream `day-in-our-data-logo/scene.json` coordinates
- Produces: the CSS custom properties every page uses; `logo.svg` as an inline-able symbol

- [ ] **Step 1: Write the tokens**

```css
/* site/styles/tokens.css */
:root {
  --ink: #102a56;
  --civic: #1559d6;
  --canopy: #14503a;
  --leaf: #2d7a55;
  --sprout: #7fb996;
  --glass: #ffc629;
  --paper: #eef2ef;
  --rule: #c9d3e4;
  --slate: #8a94a6;          /* eliminated. never red. */
  --surface: #ffffff;

  --display: "Jost", system-ui, sans-serif;
  --body: "Public Sans", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, monospace;

  --step-0: 1rem;
  --step-1: 1.25rem;
  --step-2: 1.75rem;
  --step-3: 2.5rem;
  --step-4: clamp(2.75rem, 6vw, 4.5rem);

  --gap: 1.5rem;
  --pane-radius: 2px;        /* art glass is cut, not rounded */
}
```

- [ ] **Step 2: Write the base stylesheet**

```css
/* site/styles/base.css */
@import url("https://fonts.googleapis.com/css2?family=Jost:wght@500;700;800&family=Public+Sans:wght@400;600&family=IBM+Plex+Mono:wght@400;600&display=swap");

*, *::before, *::after { box-sizing: border-box; }

body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font: var(--step-0)/1.6 var(--body);
}

h1, h2, h3 { font-family: var(--display); font-weight: 800; line-height: 1.05; margin: 0 0 .5em; }
h1 { font-size: var(--step-4); letter-spacing: -.02em; }
h2 { font-size: var(--step-3); color: var(--canopy); }
h3 { font-size: var(--step-1); }

a { color: var(--civic); }
a:focus-visible, button:focus-visible, input:focus-visible, textarea:focus-visible, select:focus-visible {
  outline: 3px solid var(--leaf);
  outline-offset: 2px;
}

.wrap { max-width: 68rem; margin: 0 auto; padding: 0 var(--gap); }

.site-nav { background: var(--surface); border-bottom: 1px solid var(--rule); }
.site-nav ul { display: flex; gap: var(--gap); list-style: none; margin: 0; padding: var(--gap) 0; }
.site-nav a { font-family: var(--display); font-weight: 700; text-decoration: none; }
.site-nav a[aria-current="page"] { border-bottom: 3px solid var(--glass); }

.ai-label {
  font: 600 .75rem/1 var(--mono);
  text-transform: uppercase;
  letter-spacing: .08em;
  color: var(--canopy);
  background: color-mix(in srgb, var(--sprout) 35%, transparent);
  padding: .35em .6em;
  border-radius: var(--pane-radius);
  display: inline-block;
}

table { border-collapse: collapse; width: 100%; }
.scroll-x { overflow-x: auto; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
```

- [ ] **Step 3: Build the logo SVG from the upstream scene**

Read `../Oak_Park_Day_in_our_Data/day-in-our-data-logo/scene.json` and translate each layer to an SVG element on a `viewBox="0 0 1800 760"` canvas. Rules:

- Ellipse layers → `<ellipse>` using `rect` as the bounding box (`cx = x + w/2`).
- Rect layers with `rotation` → `<rect>` plus `transform="rotate(deg, cx, cy)"`.
- Keep the fills exactly as the scene defines them, **including the `#e53935` line chart** — the logo is canonical and stays as published.
- Give the group `id="logo-bars"` on the three blue bars, `id="logo-line"` on the red polyline, and `id="logo-sun"` on the sun and rays, so Task 13 can animate them.
- Add `<title>Day in Our Data</title>` as the first child for screen readers.

- [ ] **Step 4: Verify the SVG renders**

Run: `python -c "import xml.etree.ElementTree as E; E.parse('site/assets/logo.svg'); print('valid xml')"`
Expected: `valid xml`

- [ ] **Step 5: Commit**

```bash
git add site/styles/ site/assets/logo.svg
git commit -m "feat: add design tokens and vector logo rebuilt from the upstream scene"
```

---

### Task 13: Submission page and showcase gallery

**Files:**
- Create: `site/index.html`, `site/styles/showcase.css`, `site/scripts/gallery.js`
- Modify: none

**Interfaces:**
- Consumes: `site/styles/tokens.css`, `base.css`, `logo.svg`, `data/submissions.json`
- Produces: the Netlify form named `submission`; the gallery renderer

- [ ] **Step 1: Write the page**

The form must carry `data-netlify="true"`, `enctype="multipart/form-data"`, and a `form-name` hidden input. One file field only (8 MB ceiling), plus the large-file fallback.

```html
<!-- site/index.html (body excerpt - full page includes <head> with the three stylesheets) -->
<header class="hero">
  <div class="wrap">
    <!-- inline the contents of site/assets/logo.svg here so the bars can animate -->
    <p class="hero__lede">
      One day. Oak Park's own data. Fifteen starter projects and whatever you bring.
    </p>
    <p class="hero__meta">
      Saturday, October 3, 2026 &middot; Dole Branch Library
    </p>
  </div>
</header>

<main class="wrap">
  <section id="submit">
    <h2>Enter your project</h2>
    <form name="submission" method="POST" data-netlify="true" enctype="multipart/form-data">
      <input type="hidden" name="form-name" value="submission" />

      <label>Team name <input type="text" name="team_name" required /></label>
      <label>Project title <input type="text" name="project_title" required /></label>

      <label>What did you build?
        <textarea name="description" rows="4" required></textarea>
      </label>

      <label>What does it solve for?
        <textarea name="solves_for" rows="3" required></textarea>
        <small>Who has this problem, and what can they do now that they could not before?</small>
      </label>

      <label>Which starter project?
        <select name="starter_project" required>
          <option value="">Choose one</option>
          <!-- 01-15 plus pitch-your-own -->
          <option value="pitch-your-own">I pitched my own</option>
        </select>
      </label>

      <label>Repository link <input type="url" name="repo_url" placeholder="https://github.com/..." /></label>
      <label>Live demo link <input type="url" name="demo_url" /></label>

      <label>One artifact
        <input type="file" name="artifact" />
        <small>
          A map, a chart, a cleaned CSV, a slide, a PDF. <strong>8 MB maximum.</strong>
          No code required &mdash; a dataset or a well-documented question is a real submission.
        </small>
      </label>

      <label>Something bigger than 8 MB?
        <input type="url" name="large_file_url" />
        <small>Paste a Drive, Dropbox, or repository release link instead.</small>
      </label>

      <button type="submit">Enter project</button>
    </form>
  </section>

  <section id="showcase">
    <h2>What teams built</h2>
    <div id="gallery" class="gallery"></div>
  </section>
</main>
```

- [ ] **Step 2: Write the gallery renderer**

```javascript
// site/scripts/gallery.js
async function renderGallery() {
  const mount = document.getElementById("gallery");
  if (!mount) return;

  let submissions = [];
  try {
    const response = await fetch("/data/submissions.json", { cache: "no-store" });
    if (!response.ok) throw new Error(String(response.status));
    submissions = await response.json();
  } catch {
    mount.innerHTML =
      '<p class="gallery__empty">The showcase opens once the first team enters a project.</p>';
    return;
  }

  if (!submissions.length) {
    mount.innerHTML =
      '<p class="gallery__empty">No projects yet. Yours can be the first.</p>';
    return;
  }

  mount.innerHTML = submissions
    .map((s) => {
      const links = [
        s.repo_url && `<a href="${s.repo_url}">Code</a>`,
        s.demo_url && `<a href="${s.demo_url}">Demo</a>`,
        s.large_file_url && `<a href="${s.large_file_url}">Files</a>`,
      ]
        .filter(Boolean)
        .join(" ");
      const art = (s.artifacts || [])
        .map((a) => `<a href="${a.url}">${a.filename}</a>`)
        .join(" ");
      return `
        <article class="pane">
          <h3>${s.project_title}</h3>
          <p class="pane__team">${s.team_name}</p>
          <p>${s.description}</p>
          <p class="pane__solves"><strong>Solves for:</strong> ${s.solves_for}</p>
          <p class="pane__links">${links} ${art}</p>
        </article>`;
    })
    .join("");
}

document.addEventListener("DOMContentLoaded", renderGallery);
```

- [ ] **Step 3: Write the showcase styles**

`site/styles/showcase.css` provides: `.hero` on `--surface` with the inline SVG capped at `min(100%, 42rem)`; a load-once animation that scales the three bars from `transform-origin: bottom` and draws `#logo-line` via `stroke-dasharray`, both suppressed under `prefers-reduced-motion`; `.gallery` as `grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr))` with `var(--gap)`; `.pane` on `--surface` with a `1px solid var(--rule)` border, `var(--pane-radius)`, and a `4px solid var(--sprout)` left edge; form inputs at full width with `1px solid var(--rule)`; the submit button `background: var(--civic)`, white text, no radius beyond `--pane-radius`.

- [ ] **Step 4: Verify locally**

Run: `cd site && python -m http.server 8000`
Open `http://localhost:8000/`. Expected: hero animates once, form renders, gallery shows the empty-state sentence (no `data/submissions.json` yet).

- [ ] **Step 5: Commit**

```bash
git add site/index.html site/styles/showcase.css site/scripts/gallery.js
git commit -m "feat: add submission form and showcase gallery"
```

---

### Task 14: Vote page

**Files:**
- Create: `site/vote.html`, `site/scripts/vote.js`

**Interfaces:**
- Consumes: `data/submissions.json`
- Produces: the Netlify form named `ballot`

- [ ] **Step 1: Write the page and script**

The form posts `code` plus `pick_1`, `pick_2`, `pick_3`. The script populates all three selects from `submissions.json` and blocks submission until three **distinct** projects are chosen — the client-side mirror of the tally's amendment-2 rule, so a voter finds out immediately rather than having their ballot silently discarded.

```html
<!-- site/vote.html (body excerpt) -->
<main class="wrap">
  <h1>Vote</h1>
  <p class="vote__lede">
    Pick your three favourite projects. Your ballot code is on the slip you were
    handed at check-in. One ballot per code.
  </p>
  <p class="ai-label">The participant vote decides the awards</p>

  <form name="ballot" method="POST" data-netlify="true" id="ballot-form">
    <input type="hidden" name="form-name" value="ballot" />
    <label>Ballot code <input type="text" name="code" required autocomplete="off" /></label>
    <label>First pick <select name="pick_1" required></select></label>
    <label>Second pick <select name="pick_2" required></select></label>
    <label>Third pick <select name="pick_3" required></select></label>
    <p id="ballot-error" class="ballot__error" role="alert" hidden></p>
    <button type="submit">Cast ballot</button>
  </form>
</main>
```

```javascript
// site/scripts/vote.js
const PICKS = ["pick_1", "pick_2", "pick_3"];

async function setupBallot() {
  const form = document.getElementById("ballot-form");
  const error = document.getElementById("ballot-error");
  if (!form) return;

  let submissions = [];
  try {
    const response = await fetch("/data/submissions.json", { cache: "no-store" });
    submissions = await response.json();
  } catch {
    error.textContent = "The project list is not available yet. Try again once the showcase is published.";
    error.hidden = false;
    return;
  }

  const options =
    '<option value="">Choose a project</option>' +
    submissions
      .map((s) => `<option value="${s.id}">${s.project_title} — ${s.team_name}</option>`)
      .join("");
  PICKS.forEach((name) => {
    form.elements[name].innerHTML = options;
  });

  form.addEventListener("submit", (event) => {
    const chosen = PICKS.map((name) => form.elements[name].value);
    if (new Set(chosen).size !== PICKS.length) {
      event.preventDefault();
      error.textContent = "Pick three different projects.";
      error.hidden = false;
      return;
    }
    error.hidden = true;
  });
}

document.addEventListener("DOMContentLoaded", setupBallot);
```

- [ ] **Step 2: Verify locally**

Run: `cd site && python -m http.server 8000`
Open `http://localhost:8000/vote.html`. Expected: with a hand-made `data/submissions.json`, the three selects populate; choosing the same project twice blocks submission with "Pick three different projects."

- [ ] **Step 3: Commit**

```bash
git add site/vote.html site/scripts/vote.js
git commit -m "feat: add ballot page with distinct-picks validation"
```

---

### Task 15: Results page — art-glass bracket and the comparison

**Files:**
- Create: `site/results.html`, `site/styles/bracket.css`, `site/scripts/results.js`

**Interfaces:**
- Consumes: `data/results/bracket.json`, `scores.json`, `comparison.json`
- Produces: the signature bracket and the comparison table

- [ ] **Step 1: Build the page structure**

Three regions in order — the comparison first, because it is the finding; the bracket second, because it is the ornament.

```html
<!-- site/results.html (body excerpt) -->
<main class="wrap">
  <h1>Results</h1>

  <section id="comparison">
    <h2>What the crowd chose, and what the machines chose</h2>
    <p class="results__standing">
      <strong>The participant vote decides the awards.</strong>
      The AI panel below ran independently and decides nothing.
    </p>
    <p class="ai-label">Panel scores are AI-generated</p>
    <div id="agreement"></div>
    <div class="scroll-x"><table id="side-by-side"></table></div>
    <div class="scroll-x"><table id="per-persona"></table></div>
  </section>

  <section id="bracket">
    <h2>The panel's bracket</h2>
    <p class="ai-label">AI-generated</p>
    <div class="scroll-x"><div id="glass" class="glass"></div></div>
  </section>
</main>
```

**Note:** remove the stray character in `vote決` — write `<strong>The participant vote decides the awards.</strong>`.

- [ ] **Step 2: Render the comparison**

```javascript
// site/scripts/results.js (comparison half)
async function loadJSON(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(path);
  return response.json();
}

function renderAgreement(comparison, titles) {
  const mount = document.getElementById("agreement");
  const rho = comparison.spearman;
  const headline =
    rho === null
      ? "Not enough variation to measure agreement."
      : `Spearman correlation <strong>${rho.toFixed(2)}</strong> across ${comparison.n} ballots.`;
  mount.innerHTML = `
    <p class="agreement">${headline}</p>
    ${comparison.caveat ? `<p class="agreement__caveat">${comparison.caveat}</p>` : ""}`;

  const side = document.getElementById("side-by-side");
  const rows = comparison.crowd_ranking
    .map((id, i) => {
      const panelAt = comparison.panel_ranking[i];
      return `<tr>
        <td class="rank">${i + 1}</td>
        <td>${titles[id] || id}</td>
        <td>${comparison.crowd_counts[id]}</td>
        <td>${titles[panelAt] || panelAt || "—"}</td>
      </tr>`;
    })
    .join("");
  side.innerHTML = `
    <caption>Crowd ranking beside the panel's</caption>
    <thead><tr><th>#</th><th>Residents chose</th><th>Votes</th><th>Panel chose</th></tr></thead>
    <tbody>${rows}</tbody>`;

  const perPersona = Object.entries(comparison.per_persona)
    .sort((a, b) => (b[1] ?? -2) - (a[1] ?? -2))
    .map(
      ([persona, value]) =>
        `<tr><td>${persona.replace(/-/g, " ")}</td><td>${
          value === null ? "—" : value.toFixed(2)
        }</td></tr>`
    )
    .join("");
  document.getElementById("per-persona").innerHTML = `
    <caption>Which judge best predicted the crowd</caption>
    <thead><tr><th>Persona</th><th>Agreement with residents</th></tr></thead>
    <tbody>${perPersona}</tbody>`;
}
```

- [ ] **Step 3: Render the bracket as art glass**

Each round is a flex column; each matchup is a `.pane` with the two entrants. Winners get `.pane--advancing` (border `var(--leaf)`, background tinted with `--sprout`); eliminated entrants get `.pane--out` (`color: var(--slate)`, no red anywhere). The champion pane gets `.pane--champion` with `background: var(--glass)`. Connectors are drawn with `::after` pseudo-elements, `2px solid var(--ink)` — the leaded cames. A matchup pane is a `<button>` that toggles a details panel listing each persona's vote, whether it survived the swap, and the reasoning.

When `bracket.mode === "ranked_list"`, skip the glass entirely and render an ordered list with the note: *"Fewer than four projects were entered, so the panel published a ranking rather than a bracket."*

- [ ] **Step 4: Verify locally against mock output**

Run:
```bash
python -m judging.run_panel --submissions tests/fixtures/submissions.json --out site/data/results --mock
cd site && python -m http.server 8000
```
Open `http://localhost:8000/results.html`. Expected: bracket renders from the six fixture submissions, matchup panes expand to show persona votes, no red pixels anywhere.

- [ ] **Step 5: Commit**

```bash
git add site/results.html site/styles/bracket.css site/scripts/results.js
git commit -m "feat: add results page with art-glass bracket and crowd-vs-panel comparison"
```

---

### Task 16: Workflows and Netlify deployment

**Files:**
- Create: `netlify.toml`, `.github/workflows/sync-submissions.yml`, `.github/workflows/judge.yml`, `.github/workflows/tally.yml`, `scripts/sync_netlify.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: everything above
- Produces: the deployed site and three dispatchable jobs

- [ ] **Step 1: Write the Netlify config**

```toml
# netlify.toml
[build]
  publish = "site"
  command = "cp -r data site/data"

[[headers]]
  for = "/*"
  [headers.values]
    X-Frame-Options = "DENY"
    X-Content-Type-Options = "nosniff"
    Referrer-Policy = "strict-origin-when-cross-origin"
```

- [ ] **Step 2: Write the sync script**

`scripts/sync_netlify.py` calls `GET https://api.netlify.com/api/v1/forms/{form_id}/submissions` with `Authorization: Bearer $NETLIFY_TOKEN`, maps each submission to the §4.1 shape, assigns `anon_id` as `P-01`, `P-02`… ordered by `submitted_at`, and writes `data/submissions.json`. Ballots from the `ballot` form are written to `data/ballots.json`. The script exits non-zero on any HTTP error so a failed sync is loud and the previous committed JSON stays valid.

- [ ] **Step 3: Write the three workflows**

```yaml
# .github/workflows/judge.yml
name: Run AI judging panel
on:
  workflow_dispatch:
    inputs:
      mock:
        description: "Dry run with no API calls"
        type: boolean
        default: false

jobs:
  judge:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e .
      - name: Run the panel
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          JUDGE_MODEL: claude-opus-5
        run: |
          python -m judging.run_panel \
            --submissions data/submissions.json \
            --out data/results \
            ${{ inputs.mock && '--mock' || '' }}
      - name: Commit results
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/results
          git diff --staged --quiet || git commit -m "chore: publish AI panel results"
          git push
```

`sync-submissions.yml` runs on `workflow_dispatch` and `schedule: - cron: "*/15 16-21 * * 6"` (every 15 minutes during Saturday event hours UTC), using `NETLIFY_TOKEN`. `tally.yml` runs on `workflow_dispatch` only, reads `BALLOT_CODES`, and writes `data/results/vote.json` and `comparison.json`.

- [ ] **Step 4: Connect Netlify and verify the deploy**

1. Netlify → Add new site → import `oak-park-cisc/day-in-our-data-showcase`.
2. Confirm build settings match `netlify.toml`.
3. Enable form detection.
4. Deploy, then submit one test entry and confirm it appears under Forms.
5. Add `NETLIFY_TOKEN`, `ANTHROPIC_API_KEY`, and `BALLOT_CODES` as repository secrets.

- [ ] **Step 5: Run the end-to-end dry run**

Run: dispatch `judge.yml` with `mock: true`.
Expected: green run; `data/results/bracket.json` committed; Netlify rebuilds; `results.html` renders — **with zero API spend**.

- [ ] **Step 6: Commit**

```bash
git add netlify.toml scripts/sync_netlify.py .github/workflows/ README.md
git commit -m "feat: add Netlify config, sync script, and the three dispatch workflows"
```

---

## Self-Review

**Spec coverage.** §3.1 flow → Tasks 13, 14, 16. §3.3 Netlify constraints → Task 13 (8 MB copy, single file field, `large_file_url`). §4.1–4.4 contracts → Tasks 2, 6, 5. §5.1 rubric → Task 7. §5.2 blind scoring and seeding ties → Tasks 3, 8. §5.3 position swap → Task 9. §5.5 transcripts → Task 10. §6.1–6.3 ballots → Tasks 11, 5. §6.4 turnout floor → Task 5. §7 comparison → Tasks 4, 11, 15. §8 error handling → Tasks 3, 5, 6, 9, 10. §9 testing → every task. §10 visual design → Tasks 12–15. §12 risks → mitigations in Tasks 5, 11, 13.

**Gaps deliberately left:** §11 Phase 2 (sandboxed preview, instant code validation) is out of scope per the spec. Fetching repository READMEs for evidence is wired through `readmes` parameters in Tasks 8 and 9 but the fetcher itself is not built — the `reduced_evidence` path in §8 means the panel runs correctly without it, and it is the first thing to add if time allows.

**Type consistency checked:** `anon_id` is the key throughout pass 1, seeding, and the bracket; `build_comparison` is the single place that translates `anon_id` → submission `id` via `id_of`, because the crowd votes on public ids while the panel works blind. `Vote` and `Pairing` are defined once in `bracket.py` and imported everywhere else.

**Placeholder scan:** clean. Task 12 step 3 and Task 15 step 3 describe transformations rather than showing final markup — both are mechanical translations from a named source file (`scene.json`) or a named data shape (`bracket.json`) with every rule and token spelled out, not deferred decisions.

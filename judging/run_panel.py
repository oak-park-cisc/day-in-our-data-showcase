from __future__ import annotations

import argparse
import json
from pathlib import Path

from judging.bracket import Pairing, SeedEntry, build_rounds, mean_score, seed_entries
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
        _write(out_dir / "transcripts" / f"score-{anon}.json", {
            "model_generated": True, "anon_id": anon, "justifications": personas,
        })

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
    champion: str | None = None

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
        _write(out_dir / "transcripts" / f"round-{round_no}.json", {
            "model_generated": True, "round": round_no, "matchups": played,
        })

        # Guard: an empty `advancing` must never reach pairing construction or
        # a final `advancing[0]` lookup. Only a non-empty, single-entry
        # `advancing` names a champion; anything else (including empty) stops
        # the loop without a winner.
        if not advancing:
            break
        if len(advancing) == 1:
            champion = advancing[0]
            break

        current = [
            Pairing(a=advancing[i], b=advancing[i + 1])
            for i in range(0, len(advancing) - 1, 2)
        ]
        round_no += 1

    _write(out_dir / "bracket.json", {
        "model_generated": True, "mode": "bracket", "ranking": ranking,
        "seeds": seed_of, "rounds": rounds_out, "champion": champion,
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
        # Pass 1 makes exactly len(submissions) * 5 client.score() calls before
        # pass 2 makes any client.compare() calls. MockJudgeClient serves both
        # from the same queue in order, so the ScoreOutput supply must be sized
        # exactly — otherwise leftover ScoreOutput entries get popped by
        # compare() and crash with AttributeError.
        canned = [ScoreOutput(score=3, justification="Mock.", evidence=["mock"])] * (
            len(submissions) * 5
        )
        canned += [MatchupOutput(winner="A", reasoning="Mock.")] * 10000
        client: JudgeClient = MockJudgeClient(canned)
    else:
        from judging.client import AnthropicJudgeClient
        client = AnthropicJudgeClient()

    run(submissions, client, args.out)
    print(f"Wrote results to {args.out}")


if __name__ == "__main__":
    main()

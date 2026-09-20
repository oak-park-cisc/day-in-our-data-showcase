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

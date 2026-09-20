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

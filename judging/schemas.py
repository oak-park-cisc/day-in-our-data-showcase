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

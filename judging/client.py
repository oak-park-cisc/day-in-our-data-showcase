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

    def _parse(
        self, system: str, user: str, output_format: type[ScoreOutput] | type[MatchupOutput]
    ):
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

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

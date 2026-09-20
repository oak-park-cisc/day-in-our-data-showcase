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

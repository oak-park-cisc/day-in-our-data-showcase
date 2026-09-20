from __future__ import annotations

from pathlib import Path

from judging.models import Submission

PERSONAS = ["civic-impact", "data-integrity", "usability-access", "craft", "continuation"]
_DIR = Path(__file__).parent / "personas"


def load_persona(name: str) -> str:
    return (_DIR / f"{name}.md").read_text(encoding="utf-8")


def _or_missing(value: str | None) -> str:
    return value if value else "(not provided)"


#: What every judge is told in place of a README, because nothing in this
#: codebase fetches one.
#:
#: The old placeholder read "(repository unavailable or not provided)". That
#: was false and it was prejudicial: `evidence_block`'s `repo_readme`
#: parameter is threaded through pass 1 and pass 2 but nothing ever passes it,
#: so a team with a working, documented repository had its link printed and
#: then a line saying that repository was unavailable. The Craft and
#: Continuation personas in particular score partly on exactly that.
#:
#: The decision was not to build a fetcher (spec D2 keeps participant code out
#: of this system, and §8's `reduced_evidence` path was never implemented --
#: the flag appears in the spec's §4.2 schema and nowhere in judging/). So the
#: fix is to state the methodology accurately: the panel read the submitted
#: text and the artifact list, and nothing else. results.html says the same
#: thing to readers.
NO_REPO_FETCH_NOTE = (
    "(Repository contents were not fetched. The panel scored the submitted text "
    "and artifacts only; a linked repository was not read, and its absence here "
    "says nothing about whether it exists or works.)"
)


def evidence_block(sub: Submission, repo_readme: str | None = None) -> str:
    """Everything a judge sees. Team name deliberately excluded - pass 1 is blind."""
    artifacts = "\n".join(f"  - {a.filename} ({a.bytes} bytes)" for a in sub.artifacts) or "  (none)"
    readme = repo_readme.strip() if repo_readme else NO_REPO_FETCH_NOTE
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

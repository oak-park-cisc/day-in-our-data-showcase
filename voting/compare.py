"""Builds the crowd-vs-panel comparison: the central output of the showcase.

The AI panel judges submissions blind, knowing them only by anon_id
(P-01, P-02, ...). Residents vote on public submission ids (sub_001, ...).
``build_comparison`` is the only place in the codebase where those two
namespaces meet, via the ``id_of`` mapping (anon_id -> submission id).
Everything this function returns is keyed by the PUBLIC submission id,
because that is what the site renders. Get the translation wrong here and
every downstream lookup misses silently.
"""
from __future__ import annotations

from voting.ranking import DEFAULT_AWARD_COUNT, ranking_summary
from voting.stats import spearman
from voting.tally import TallyResult

CAVEAT = (
    "Fewer than 10 valid ballots were cast. The crowd ranking is indicative only "
    "and the correlation below should not be read as a result."
)


def _panel_means(scores: dict[str, dict[str, int]]) -> dict[str, float]:
    """Mean score per anon_id, averaged across judge personas."""
    return {anon_id: sum(p.values()) / len(p) for anon_id, p in scores.items() if p}


def _rounded(correlation: float | None) -> float | None:
    """Round a correlation for display, without turning "undefined" into a number.

    spearman() computes Pearson-on-ranks via two independent sqrt() calls, so a
    mathematically exact +-1.0 can come back as e.g. 0.9999999999999998. Round
    to 6 places to absorb that float noise; None (undefined correlation) is
    passed through untouched rather than coerced to 0.0.
    """
    return None if correlation is None else round(correlation, 6)


def build_comparison(
    result: TallyResult,
    scores: dict[str, dict[str, int]],
    bracket_ranking: list[str],
    id_of: dict[str, str],
    award_count: int = DEFAULT_AWARD_COUNT,
) -> dict:
    """Crowd ranking beside the panel's, with agreement statistics.

    Args:
        result: crowd tally, counts keyed by PUBLIC submission id.
        scores: panel scores, {anon_id: {persona: score}} - keyed by anon_id,
            the panel's namespace.
        bracket_ranking: the panel's overall ranking, as a list of anon_ids.
        id_of: anon_id -> submission id. The one translation point between
            the panel's blind namespace and the public namespace the site
            renders.
        award_count: how many projects receive gift cards. Not fixed by the
            spec - see voting/ranking.py's module docstring.

    Everything in the returned dict is keyed by submission id.
    """
    crowd = dict(result.counts)
    # Ties share a rank and are never broken by submission id (spec 6.3).
    # `crowd_ranking` is display order only; `crowd_ranks` is what says who
    # placed where, and a renderer that ignores it re-invents the ordinals
    # this is here to prevent.
    crowd_rank = ranking_summary(crowd, award_count=award_count)

    # Translate the panel's per-anon_id means into the public namespace.
    # This is the only place scores cross from the panel's blind ids into
    # submission ids - get it wrong and every later lookup misses.
    panel_by_id = {id_of[anon_id]: mean for anon_id, mean in _panel_means(scores).items() if anon_id in id_of}

    personas = sorted({p for per in scores.values() for p in per})
    per_persona: dict[str, float | None] = {}
    for persona in personas:
        vals = {
            id_of[anon_id]: per[persona]
            for anon_id, per in scores.items()
            if persona in per and anon_id in id_of
        }
        # spearman() already ranks only the intersection of its two dicts'
        # keys and returns None (not 0.0) when correlation is undefined -
        # no pre-filtering needed here, and None must propagate untouched.
        per_persona[persona] = _rounded(spearman(crowd, vals))

    return {
        "model_generated_panel": True,
        "awards_determined_by": "participant vote",
        "crowd_ranking": crowd_rank["ranking"],
        "crowd_ranks": crowd_rank["ranks"],
        "crowd_ties": crowd_rank["ties"],
        "award_count": crowd_rank["award_count"],
        "award_boundary_tie": crowd_rank["award_boundary_tie"],
        "award_boundary_tie_ids": crowd_rank["award_boundary_tie_ids"],
        "crowd_counts": crowd,
        "panel_ranking": [id_of[anon_id] for anon_id in bracket_ranking if anon_id in id_of],
        "panel_means": panel_by_id,
        "spearman": _rounded(spearman(crowd, panel_by_id)),
        "per_persona": per_persona,
        "n": result.valid,
        "invalid_ballots": result.invalid,
        "indicative": result.indicative,
        "caveat": CAVEAT if result.indicative else "",
    }

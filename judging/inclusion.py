"""The single rule for which submissions the panel is deemed to have scored.

This module exists because two modules used to disagree about it.
``judging/run_panel.py`` required all five personas before a submission could
be seeded, bracketed or ranked; ``voting/compare.py`` accepted any non-empty
score dict. A submission where one persona abstained twice therefore vanished
from the panel's ranking while its mean still entered the headline
correlation -- averaged over 2 personas, compared against everyone else's 5.
That is not a smaller sample, it is a different measurement wearing the same
label.

The rule, applied identically in both places: a submission counts as scored by
the panel only when every persona in ``judging.prompts.PERSONAS`` returned a
score for it. Anything short of that is excluded from seeding, the bracket,
the panel ranking, the panel mean, the headline correlation and the
per-persona correlations -- and is DISCLOSED on the results page, because
spec §8 requires an abstention path be "shown in the UI. Never silent."
"""
from __future__ import annotations

from judging.prompts import PERSONAS

#: Every persona must have returned a score. Derived from PERSONAS rather
#: than hardcoded as `len(...) == 5`, so adding a sixth judge does not
#: silently start admitting five-persona submissions.
REQUIRED_PERSONAS = frozenset(PERSONAS)


def panel_scored(persona_scores: dict[str, int] | None) -> bool:
    """True when every required persona scored this submission."""
    return bool(persona_scores) and REQUIRED_PERSONAS.issubset(persona_scores)


def split_scored(
    scores: dict[str, dict[str, int]],
) -> tuple[dict[str, dict[str, int]], list[str]]:
    """Partition {anon_id: {persona: score}} into (fully scored, excluded ids).

    The excluded list is sorted so the disclosure on the page is stable
    between runs.
    """
    included = {anon_id: per for anon_id, per in scores.items() if panel_scored(per)}
    excluded = sorted(anon_id for anon_id in scores if anon_id not in included)
    return included, excluded

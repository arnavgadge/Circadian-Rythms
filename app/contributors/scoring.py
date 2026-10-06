"""The composite contributor score.

Locked architecture for a signal with **both** a normalized phase
effect and an alignment deficit (evening screen, morning light, meal
timing):

    contributor_score = 0.60 * normalized_phase_effect + 0.40 * alignment_deficit

Two signals are missing one of those two inputs, by construction, and
each falls back to the other input alone rather than a fabricated
value for the missing one (documented explicitly, in both directions,
since the brief only spelled out the exercise case):

- **exercise** has a phase effect (Phase 6's model) but no Phase 8
  alignment component -> ``contributor_score = 1.00 * normalized_phase_effect``.
- **social jetlag** has a Phase 8 alignment component but no
  established phase-shift-effect formula in Phase 3/6 (jetlag was
  modeled there as a consistency/consequence measure, not a direct
  DLMO-shifting input like light/screen/meal/exercise) ->
  ``contributor_score = 1.00 * alignment_deficit``.

This mirror-image treatment was chosen specifically so neither
direction of missing data is patched over with an invented number.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.contributors.config import DEFAULT_CONTRIBUTOR_CONFIG, ContributorConfig

SIGNALS_PHASE_EFFECT_ONLY = ("exercise",)
SIGNALS_DEFICIT_ONLY = ("social_jetlag",)


@dataclass(frozen=True)
class ScoreComponents:
    contributor_score: Optional[float]
    weight_used: str  # "composite" | "phase_effect_only" | "deficit_only" | "unavailable"


def compute_contributor_score(
    signal: str,
    normalized_phase_effect: Optional[float],
    alignment_deficit: Optional[float],
    config: ContributorConfig = DEFAULT_CONTRIBUTOR_CONFIG,
) -> ScoreComponents:
    if signal in SIGNALS_PHASE_EFFECT_ONLY:
        if normalized_phase_effect is None:
            return ScoreComponents(None, "unavailable")
        return ScoreComponents(normalized_phase_effect, "phase_effect_only")

    if signal in SIGNALS_DEFICIT_ONLY:
        if alignment_deficit is None:
            return ScoreComponents(None, "unavailable")
        return ScoreComponents(alignment_deficit, "deficit_only")

    # Composite signals: both inputs are required for the full 60/40
    # formula; if one is missing, fall back to the other alone rather
    # than silently treating the missing one as zero (which would bias
    # the score downward for no principled reason).
    if normalized_phase_effect is not None and alignment_deficit is not None:
        score = config.phase_effect_weight * normalized_phase_effect + config.alignment_deficit_weight * alignment_deficit
        return ScoreComponents(score, "composite")
    if normalized_phase_effect is not None:
        return ScoreComponents(normalized_phase_effect, "phase_effect_only")
    if alignment_deficit is not None:
        return ScoreComponents(alignment_deficit, "deficit_only")
    return ScoreComponents(None, "unavailable")

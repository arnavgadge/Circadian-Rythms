r"""The intervention lifecycle: a small, explicit state machine derived
from ``intervention_log`` rows and (optionally) an already-computed
effect evaluation -- never a stored column, since it is fully
reconstructable from existing facts (see
``docs/intervention_effectiveness.md`` "Intervention lifecycle").

    RECOMMENDED -> ACTIVE -> OBSERVED -> EVALUATED
                         \-> INSUFFICIENT_DATA / WAITING_FOR_HISTORY
"""

from __future__ import annotations

from typing import Optional

from app.effectiveness.windows import INSUFFICIENT_BASELINE_HISTORY
from app.effectiveness.windows import InterventionEpisode

RECOMMENDED = "RECOMMENDED"
ACTIVE = "ACTIVE"
OBSERVED = "OBSERVED"
EVALUATED = "EVALUATED"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
WAITING_FOR_HISTORY = "WAITING_FOR_HISTORY"


def compute_lifecycle_status(
    episode: InterventionEpisode,
    is_current: bool,
    effect_result: Optional[object] = None,  # app.effectiveness.dispatcher.InterventionEffectResult
) -> str:
    if effect_result is not None:
        if effect_result.chosen_phase is not None:
            return EVALUATED
        if effect_result.phase1.insufficiency_reason == INSUFFICIENT_BASELINE_HISTORY:
            return WAITING_FOR_HISTORY
        return INSUFFICIENT_DATA

    if is_current:
        return RECOMMENDED if len(episode.log_dates) <= 1 else ACTIVE
    return OBSERVED

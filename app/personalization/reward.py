"""Bandit reward: combines observed improvement with compliance,
using the **same signed-DLMO convention already established**
throughout Phases 6-9: positive minutes = delay (later), negative =
advance (earlier); a positive ``phase_deviation_minutes`` (Phase 8)
means the participant is currently too delayed and needs an advance.

"Improvement" is therefore relative to what *this participant* needs,
never a blind "negative = good" rule -- an intervention that advances
someone who is already too advanced is not an improvement, exactly the
same "aggravating vs. corrective" logic Phase 9's direction
classification already uses (see ``app.contributors.direction`), just
expressed here as a continuous reward magnitude rather than a
category label.
"""

from __future__ import annotations

from typing import Optional


def compute_reward(
    signed_effect_minutes: Optional[float], phase_deviation_minutes: Optional[float], compliance: Optional[float]
) -> Optional[float]:
    """``None`` if any input is missing -- a reward is never fabricated
    for an observation that cannot actually be computed."""

    if signed_effect_minutes is None or phase_deviation_minutes is None or compliance is None:
        return None
    if phase_deviation_minutes == 0:
        return 0.0

    corrective_sign = -1.0 if phase_deviation_minutes > 0 else 1.0
    benefit_minutes = signed_effect_minutes * corrective_sign
    return benefit_minutes * compliance

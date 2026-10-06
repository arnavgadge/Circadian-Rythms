"""Structured user-facing feedback data -- no natural-language
generation, only fixed, phase-appropriate labels and caveats filled
with already-computed structured values. A later UI phase decides how
to render this; this module only assembles what it would need.

Terminology is locked to the measurement phase actually used (never
"caused"):

- Phase 1 -> "Observed change"
- Phase 2 -> "Change compared with a similar previous period"
- Phase 3 -> "Estimated personal effect"
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.effectiveness.dispatcher import InterventionEffectResult

PHASE_LABELS = {
    1: "Observed change",
    2: "Change compared with a similar previous period",
    3: "Estimated personal effect",
}

CONFOUND_CAVEAT = (
    "Other behaviors also changed during this period; the observed change may be shared across factors."
)


@dataclass(frozen=True)
class UserFacingFeedback:
    intervention_id: int
    compliant_days: int
    observed_days: int
    before_dlmo_hour: Optional[float]
    before_alignment_score: Optional[float]
    after_dlmo_hour: Optional[float]
    after_alignment_score: Optional[float]
    estimated_improvement_minutes: Optional[float]
    phase_label: str
    caveats: tuple


def build_user_facing_feedback(result: InterventionEffectResult) -> Optional[UserFacingFeedback]:
    """``None`` if even Phase 1 lacks sufficient data -- there is
    nothing yet to show the user."""

    if result.chosen_phase is None:
        return None

    p1 = result.phase1
    caveats = [CONFOUND_CAVEAT] if p1.confound_flag else []

    if result.chosen_phase == 3:
        improvement = result.phase3.effect_mins_per_compliance_unit
    elif result.chosen_phase == 2:
        improvement = result.phase2.mean_dlmo_difference
    else:
        improvement = p1.effect_estimate

    return UserFacingFeedback(
        intervention_id=p1.intervention_id,
        compliant_days=p1.compliance_days,
        observed_days=p1.observed_days,
        before_dlmo_hour=p1.baseline_dlmo,
        before_alignment_score=p1.baseline_alignment,
        after_dlmo_hour=p1.recent_dlmo,
        after_alignment_score=p1.recent_alignment,
        estimated_improvement_minutes=improvement,
        phase_label=PHASE_LABELS[result.chosen_phase],
        caveats=tuple(caveats),
    )

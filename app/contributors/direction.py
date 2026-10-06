"""Direction classification: HURTING / OPPORTUNITY_MISSED / NEUTRAL.

Direction is interpreted **relative to the participant's current phase
deviation** (Phase 8's ``phase_difference_minutes``: positive means
actual sleep is later than ideal, i.e. the participant is currently
too delayed and needs an advance; negative means too advanced and
needs a delay) -- never a blind "negative effect = good" rule.

- **HURTING**: the signal's effect pushes in the *same* direction as
  the existing deviation (making the misalignment worse).
- **OPPORTUNITY_MISSED**: the signal's effect pushes in the
  *corrective* direction, but only weakly -- a chance to help that
  isn't being used to its potential.
- **NEUTRAL**: the participant is already close to aligned (nothing
  meaningful to correct), the signal's own score is below the
  significance threshold, the signal has no phase-effect direction to
  compare (social jetlag), or its corrective effect is already
  meaningfully large (it is already doing its job).
"""

from __future__ import annotations

from typing import Optional

from app.contributors.config import DEFAULT_CONTRIBUTOR_CONFIG, ContributorConfig

HURTING = "hurting"
OPPORTUNITY_MISSED = "opportunity_missed"
NEUTRAL = "neutral"


def classify_direction(
    signed_phase_effect_minutes: Optional[float],
    phase_deviation_minutes: Optional[float],
    contributor_score: Optional[float],
    config: ContributorConfig = DEFAULT_CONTRIBUTOR_CONFIG,
) -> str:
    if contributor_score is None or contributor_score < config.significance_threshold:
        return NEUTRAL

    # No phase-effect direction available (e.g. social jetlag, or an
    # effect-bearing signal with no data this window): direction can
    # only ever be "hurting" (a large deficit) or neutral, never an
    # "opportunity missed", since there is no corrective-direction
    # concept without a signed effect.
    if signed_phase_effect_minutes is None:
        return HURTING

    if phase_deviation_minutes is None or abs(phase_deviation_minutes) < config.phase_deviation_neutral_zone_minutes:
        return NEUTRAL

    aggravating = (signed_phase_effect_minutes > 0) == (phase_deviation_minutes > 0)
    if aggravating:
        return HURTING

    if abs(signed_phase_effect_minutes) < config.weak_corrective_effect_minutes_threshold:
        return OPPORTUNITY_MISSED

    return NEUTRAL  # already correcting meaningfully; not a problem contributor

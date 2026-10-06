"""Model validity checks for the Phase 2 personal effect model.

Never trust a personal effect estimate just because a participant has
"enough rows" -- every check here must pass before the estimate is
used at any weight above the blended default (see
``docs/personalization_engine.md`` "Model validity checks").
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Optional, Sequence

from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG, PersonalizationConfig


@dataclass(frozen=True)
class ModelValidityResult:
    valid: bool
    reasons: tuple = field(default_factory=tuple)


def check_model_validity(
    slope: Optional[float],
    intercept: Optional[float],
    r_squared: Optional[float],
    n_observations: int,
    confidence_interval_lower: Optional[float],
    confidence_interval_upper: Optional[float],
    compliance_values: Sequence,
    config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG,
) -> ModelValidityResult:
    reasons: list = []

    if n_observations < config.effect_model_min_observations:
        reasons.append("insufficient_observations")

    if slope is None or not math.isfinite(slope):
        reasons.append("non_finite_slope")
    elif abs(slope) > config.max_plausible_effect_minutes:
        reasons.append("implausible_effect_magnitude")

    if intercept is not None and not math.isfinite(intercept):
        reasons.append("non_finite_intercept")

    if r_squared is not None and r_squared < config.min_r_squared_for_validity:
        reasons.append("poor_fit")

    if confidence_interval_lower is not None and confidence_interval_upper is not None:
        if (confidence_interval_upper - confidence_interval_lower) > config.max_confidence_interval_width_minutes:
            reasons.append("confidence_interval_too_wide")

    present_compliance = [v for v in compliance_values if v is not None]
    if len(present_compliance) < 2:
        reasons.append("insufficient_compliance_variation")
    elif statistics.pstdev(present_compliance) < config.min_compliance_variation:
        reasons.append("degenerate_compliance_values")

    return ModelValidityResult(valid=len(reasons) == 0, reasons=tuple(reasons))

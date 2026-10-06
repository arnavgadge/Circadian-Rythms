"""Intervention-specific compliance scoring.

One shared, transparent directional-decay computation
(:func:`_directional_compliance`) parameterized by each intervention's
own ``value_kind``/``direction`` metadata (reused directly from
``app.recommendations.catalogue`` -- never redefined) plus a
per-intervention-type decay constant
(``EffectivenessConfig.compliance_decay_by_intervention_type``).
Thin, named per-signal wrappers make the "one evaluator per
intervention type" contract explicit and extensible without
duplicating the core math in a giant function.

**Compliance is asymmetric, not a symmetric decay around the target**:
being at-or-past the target *in the desired direction* is full
compliance (``1.0``) regardless of how far past; only falling short
(on the wrong side of the target) degrades the score. This matches the
worked example in the brief: a screen cutoff of midnight with actual
screens-off at 23:45 (15 min *early*) is full compliance, while 00:15
(15 min *late*) is only partial -- the two are not symmetric.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from app.effectiveness.config import DEFAULT_EFFECTIVENESS_CONFIG, EffectivenessConfig
from app.recommendations.catalogue import CLOCK_HOUR, CandidateIntervention, direction_sign
from app.synthetic.time_utils import circular_diff_hours


@dataclass(frozen=True)
class ComplianceResult:
    signal: str
    available: bool
    compliance_degree: Optional[float]  # 0.0-1.0
    compliance_binary: Optional[bool]
    deviation: Optional[float]  # actual - target, minutes (native unit for non-clock signals)
    method: str


def _unavailable(signal: str) -> ComplianceResult:
    return ComplianceResult(signal, False, None, None, None, "unavailable")


def _directional_compliance(
    signal: str,
    target_value: Optional[float],
    actual_value: Optional[float],
    value_kind: str,
    direction: str,
    decay: float,
    config: EffectivenessConfig,
) -> ComplianceResult:
    if target_value is None or actual_value is None:
        return _unavailable(signal)

    if value_kind == CLOCK_HOUR:
        deviation_minutes = circular_diff_hours(actual_value, target_value) * 60.0
    else:
        deviation_minutes = actual_value - target_value

    # direction_sign < 0 (earlier/decrease): compliant when actual is
    # at or before target, i.e. deviation <= 0; direction_sign > 0
    # (later/increase): compliant when actual is at or beyond target.
    shortfall = deviation_minutes if direction_sign(direction) < 0 else -deviation_minutes

    if shortfall <= 0:
        degree = 1.0
    else:
        degree = math.exp(-shortfall / decay)

    binary = degree >= config.compliance_binary_threshold
    return ComplianceResult(signal, True, degree, binary, deviation_minutes, "directional_decay")


def evaluate_screen_cutoff_compliance(
    target_hour: Optional[float], actual_hour: Optional[float], config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG
) -> ComplianceResult:
    return _directional_compliance(
        "evening_screen", target_hour, actual_hour, CLOCK_HOUR, "earlier",
        config.compliance_decay_by_intervention_type["screen"], config,
    )


def evaluate_morning_light_compliance(
    target_minutes: Optional[float], actual_minutes: Optional[float], config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG
) -> ComplianceResult:
    return _directional_compliance(
        "morning_light", target_minutes, actual_minutes, "duration_minutes", "increase",
        config.compliance_decay_by_intervention_type["light"], config,
    )


def evaluate_meal_timing_compliance(
    target_hour: Optional[float], actual_hour: Optional[float], config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG
) -> ComplianceResult:
    return _directional_compliance(
        "meal_timing", target_hour, actual_hour, CLOCK_HOUR, "earlier",
        config.compliance_decay_by_intervention_type["meal"], config,
    )


def evaluate_exercise_compliance(
    target_hour: Optional[float], actual_hour: Optional[float], config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG
) -> ComplianceResult:
    return _directional_compliance(
        "exercise", target_hour, actual_hour, CLOCK_HOUR, "earlier",
        config.compliance_decay_by_intervention_type["exercise"], config,
    )


def evaluate_caffeine_compliance(
    target_hour: Optional[float], actual_hour: Optional[float], config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG
) -> ComplianceResult:
    return _directional_compliance(
        "caffeine", target_hour, actual_hour, CLOCK_HOUR, "earlier",
        config.compliance_decay_by_intervention_type["caffeine"], config,
    )


def evaluate_social_jetlag_compliance(
    target_minutes: Optional[float], actual_minutes: Optional[float], config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG
) -> ComplianceResult:
    """Jetlag compliance is only ever observable on free days (Phase
    3/4 only record ``social_jetlag_minutes`` then) -- ``actual_minutes
    = None`` on a non-free day is a **missing observation**, not
    non-compliance (see ``docs/intervention_effectiveness.md``
    "Missing data")."""

    return _directional_compliance(
        "social_jetlag", target_minutes, actual_minutes, "duration_minutes", "decrease",
        config.compliance_decay_by_intervention_type["sleep"], config,
    )


_EVALUATORS = {
    "evening_screen": evaluate_screen_cutoff_compliance,
    "morning_light": evaluate_morning_light_compliance,
    "meal_timing": evaluate_meal_timing_compliance,
    "exercise": evaluate_exercise_compliance,
    "social_jetlag": evaluate_social_jetlag_compliance,
    # Caffeine has no Phase 9 contributor signal (see
    # app.recommendations.catalogue / the seeded REDUCE_LATE_CAFFEINE
    # entry), so callers dispatch to it by intervention_type instead of
    # a contributor-signal name -- see resolve_dispatch_key below.
    "caffeine": evaluate_caffeine_compliance,
}


def resolve_dispatch_key(contributor_signals: tuple, intervention_type: str) -> str:
    """The key ``evaluate_compliance`` dispatches on: the intervention's
    own contributor signal where it has one, else its catalogue
    ``intervention_type`` (currently only relevant for caffeine)."""

    return contributor_signals[0] if contributor_signals else intervention_type


def evaluate_compliance(
    signal: str,
    target_value: Optional[float],
    actual_value: Optional[float],
    config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG,
) -> ComplianceResult:
    """Dispatch to the named evaluator for ``signal`` (see
    :func:`resolve_dispatch_key`)."""

    evaluator = _EVALUATORS.get(signal)
    if evaluator is None:
        return _unavailable(signal)
    return evaluator(target_value, actual_value, config)

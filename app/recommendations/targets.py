"""Graduated target calculation.

**Locked rule**: never ask the participant to jump straight to the
theoretically ideal value. Target roughly halfway between their
current behavior and the desired value
(``RecommendationConfig.graduated_target_fraction``, default 0.50).

Clock-time-valued behaviors (screen cutoff, meal time, exercise time)
use the existing circular-time utilities
(``app.synthetic.time_utils``) so a gap that crosses midnight is
interpreted as the short way around, never as a naive 20+ hour linear
difference. Plain-magnitude behaviors (light duration, jetlag minutes)
use ordinary linear interpolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.recommendations.catalogue import CLOCK_HOUR, CandidateIntervention, direction_sign
from app.synthetic.time_utils import add_hours, circular_diff_hours


@dataclass(frozen=True)
class GraduatedTarget:
    current_value: float
    desired_value: float
    target_value: float
    raw_gap: float  # desired - current, signed, in the value's own unit (hours for clock_hour)
    applied_shift: float  # the (possibly bound-clipped) shift actually applied
    bound_clipped: bool
    wrong_direction_clamped: bool  # True if current already at/past the desired direction


def _resolve_desired_value(candidate: CandidateIntervention, ideal_sleep_onset_hour: Optional[float]) -> float:
    if candidate.desired_value_relative_to == "ideal_sleep_onset":
        if ideal_sleep_onset_hour is None:
            raise ValueError(
                f"{candidate.intervention_code}: desired value is relative to ideal_sleep_onset, "
                "but no ideal_sleep_onset_hour was supplied"
            )
        return add_hours(ideal_sleep_onset_hour, candidate.desired_value_assumption)
    return candidate.desired_value_assumption


def compute_graduated_target(
    candidate: CandidateIntervention,
    current_value: float,
    ideal_sleep_onset_hour: Optional[float],
    fraction: float,
) -> GraduatedTarget:
    desired_value = _resolve_desired_value(candidate, ideal_sleep_onset_hour)
    is_circular = candidate.value_kind == CLOCK_HOUR

    if is_circular:
        raw_gap = circular_diff_hours(desired_value, current_value)
    else:
        raw_gap = desired_value - current_value

    expected_sign = direction_sign(candidate.direction)
    wrong_direction_clamped = False
    if raw_gap != 0.0 and (raw_gap > 0) != (expected_sign > 0):
        # Current behavior is already at or past the intervention's own
        # desired direction (e.g. screen cutoff already earlier than the
        # target) -- never recommend moving backwards to "catch up" to a
        # now-stale desired value.
        wrong_direction_clamped = True
        raw_gap = 0.0

    shift = fraction * raw_gap
    bound_clipped = False
    if abs(shift) > candidate.max_shift_per_recommendation:
        shift = candidate.max_shift_per_recommendation * (1 if shift > 0 else -1)
        bound_clipped = True

    if is_circular:
        target_value = add_hours(current_value, shift)
    else:
        target_value = current_value + shift
        if candidate.min_target_value is not None and target_value < candidate.min_target_value:
            target_value = candidate.min_target_value
            bound_clipped = True
        if candidate.max_target_value is not None and target_value > candidate.max_target_value:
            target_value = candidate.max_target_value
            bound_clipped = True

    return GraduatedTarget(
        current_value=current_value,
        desired_value=desired_value,
        target_value=target_value,
        raw_gap=raw_gap,
        applied_shift=shift,
        bound_clipped=bound_clipped,
        wrong_direction_clamped=wrong_direction_clamped,
    )

"""Phase 2: within-person matched-period observational comparison.

Finds a **prior** period for the *same* participant whose non-target
behaviors looked similar to the intervention period, so the target
behavior is the main thing that differs -- a still-observational, but
better-controlled comparison than a plain before/after (Phase 1).
Never matches across different participants.

**Labeled MATCHED_OBSERVATIONAL** -- still not a causal claim; matching
on observed covariates cannot rule out unobserved confounds the way a
randomized or regression-controlled design can (Phase 3).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, replace
from datetime import date as date_cls, timedelta
from typing import Optional

from app.effectiveness.config import DEFAULT_EFFECTIVENESS_CONFIG, EffectivenessConfig, MATCHED_OBSERVATIONAL
from app.effectiveness.outcomes import (
    SIGNAL_VALUE_KIND,
    alignment_change as _alignment_change,
    dlmo_change_minutes as _dlmo_change_minutes,
    period_mean_alignment_score,
    period_mean_dlmo_hour,
    signal_period_mean,
)
from app.effectiveness.phase1 import DayRecord
from app.effectiveness.windows import Period
from app.recommendations.catalogue import CLOCK_HOUR
from app.synthetic.time_utils import circular_diff_hours, circular_std_hours

INSUFFICIENT_HISTORY_FOR_MATCHING = "insufficient_history_for_matching"
NO_ACCEPTABLE_MATCH = "no_acceptable_match"

_NON_TARGET_CANDIDATES = ("evening_screen", "morning_light", "meal_timing", "exercise", "social_jetlag")


@dataclass(frozen=True)
class MatchQuality:
    matched_period_start: date_cls
    matched_period_end: date_cls
    similarity_score: float  # standardized mean distance across matched variables; lower is better
    variables_matched: tuple
    target_variable_excluded: str
    data_completeness: float
    match_valid: bool


@dataclass(frozen=True)
class InterventionEffectPhase2:
    intervention_id: int
    participant_id: int
    match_quality: Optional[MatchQuality]

    matched_mean_dlmo: Optional[float]
    intervention_mean_dlmo: Optional[float]
    mean_dlmo_difference: Optional[float]

    matched_slope_minutes_per_day: Optional[float]
    intervention_slope_minutes_per_day: Optional[float]
    slope_difference: Optional[float]

    matched_mean_alignment: Optional[float]
    intervention_mean_alignment: Optional[float]
    mean_alignment_difference: Optional[float]

    measurement_phase: int
    interpretation: str

    sufficient_data: bool
    insufficiency_reason: Optional[str] = None


def _insufficient(intervention_id: int, participant_id: int, reason: str) -> InterventionEffectPhase2:
    return InterventionEffectPhase2(
        intervention_id=intervention_id, participant_id=participant_id, match_quality=None,
        matched_mean_dlmo=None, intervention_mean_dlmo=None, mean_dlmo_difference=None,
        matched_slope_minutes_per_day=None, intervention_slope_minutes_per_day=None, slope_difference=None,
        matched_mean_alignment=None, intervention_mean_alignment=None, mean_alignment_difference=None,
        measurement_phase=2, interpretation=MATCHED_OBSERVATIONAL,
        sufficient_data=False, insufficiency_reason=reason,
    )


def _unwrap_circular_series(hours: list) -> list:
    if not hours:
        return []
    unwrapped = [hours[0]]
    for h in hours[1:]:
        unwrapped.append(unwrapped[-1] + circular_diff_hours(h, unwrapped[-1] % 24.0))
    return unwrapped


def _ols_slope(y: list) -> Optional[float]:
    """Ordinary-least-squares slope of ``y`` against day index -- a
    plain descriptive trajectory statistic, not Phase 3's effect
    estimator. Returns ``None`` for fewer than 2 points."""

    n = len(y)
    if n < 2:
        return None
    x = list(range(n))
    x_mean, y_mean = sum(x) / n, sum(y) / n
    covariance = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    variance = sum((xi - x_mean) ** 2 for xi in x)
    if variance <= 1e-12:
        return None
    return covariance / variance


def _dlmo_slope_per_day(dlmo_hours: list) -> Optional[float]:
    present = [h for h in dlmo_hours if h is not None]
    if len(present) < 2:
        return None
    unwrapped = _unwrap_circular_series(present)
    slope_hours_per_day = _ols_slope(unwrapped)
    return slope_hours_per_day * 60.0 if slope_hours_per_day is not None else None


def _signal_std(signal: str, values: list) -> float:
    present = [v for v in values if v is not None]
    if len(present) < 2:
        return 0.0
    if SIGNAL_VALUE_KIND[signal] == CLOCK_HOUR:
        return circular_std_hours(present)
    return statistics.stdev(present)


def _standardized_distance(signal: str, mean_a: Optional[float], mean_b: Optional[float], std: float) -> Optional[float]:
    if mean_a is None or mean_b is None:
        return None
    diff = abs(circular_diff_hours(mean_a, mean_b)) if SIGNAL_VALUE_KIND[signal] == CLOCK_HOUR else abs(mean_a - mean_b)
    return diff / std if std > 1e-6 else diff


def find_matched_period(
    history: dict,  # date -> DayRecord, the participant's full available history
    intervention_period: Period,
    target_signal: str,
    config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG,
) -> Optional[MatchQuality]:
    matched_variables = tuple(s for s in _NON_TARGET_CANDIDATES if s != target_signal)
    window_len = max(len(intervention_period.observed_dates), config.min_matched_period_days)

    all_dates = sorted(history.keys())
    if not all_dates:
        return None

    intervention_records = [history[d] for d in intervention_period.observed_dates]
    intervention_means = {
        s: signal_period_mean(s, [r.signal_values.get(s) for r in intervention_records]) for s in matched_variables
    }
    signal_stds = {
        s: _signal_std(s, [r.signal_values.get(s) for r in history.values()]) for s in matched_variables
    }

    best: Optional[MatchQuality] = None
    best_distance = None

    for start in all_dates:
        end = start + timedelta(days=window_len - 1)
        if end >= intervention_period.start_date:
            continue  # must not overlap or follow the intervention period

        window_dates = _date_range(start, end)
        observed = [d for d in window_dates if d in history]
        completeness = len(observed) / window_len
        if completeness < config.min_match_data_completeness:
            continue

        window_records = [history[d] for d in observed]
        distances = []
        for signal in matched_variables:
            window_mean = signal_period_mean(signal, [r.signal_values.get(signal) for r in window_records])
            distance = _standardized_distance(signal, window_mean, intervention_means.get(signal), signal_stds[signal])
            if distance is not None:
                distances.append(distance)

        if not distances:
            continue
        mean_distance = sum(distances) / len(distances)

        if best_distance is None or mean_distance < best_distance:
            best_distance = mean_distance
            best = MatchQuality(
                matched_period_start=start,
                matched_period_end=end,
                similarity_score=mean_distance,
                variables_matched=matched_variables,
                target_variable_excluded=target_signal,
                data_completeness=completeness,
                match_valid=mean_distance <= config.max_match_distance,
            )

    return best


def _date_range(start: date_cls, end: date_cls) -> list:
    days = (end - start).days
    return [start + timedelta(days=i) for i in range(days + 1)]


def evaluate_phase2_effect(
    intervention_id: int,
    participant_id: int,
    target_signal: str,
    history: dict,  # date -> DayRecord
    intervention_period: Period,
    config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG,
) -> InterventionEffectPhase2:
    if len(history) < config.min_history_days_for_phase2:
        return _insufficient(intervention_id, participant_id, INSUFFICIENT_HISTORY_FOR_MATCHING)

    match = find_matched_period(history, intervention_period, target_signal, config)
    if match is None or not match.match_valid:
        result = _insufficient(intervention_id, participant_id, NO_ACCEPTABLE_MATCH)
        return replace(result, match_quality=match)

    matched_dates = _date_range(match.matched_period_start, match.matched_period_end)
    matched_records = [history[d] for d in matched_dates if d in history]
    intervention_records = [history[d] for d in intervention_period.observed_dates]

    matched_dlmo_series = [r.dlmo_hour for r in matched_records]
    intervention_dlmo_series = [r.dlmo_hour for r in intervention_records]

    matched_mean_dlmo = period_mean_dlmo_hour(matched_dlmo_series)
    intervention_mean_dlmo = period_mean_dlmo_hour(intervention_dlmo_series)
    matched_mean_alignment = period_mean_alignment_score([r.alignment_score for r in matched_records])
    intervention_mean_alignment = period_mean_alignment_score([r.alignment_score for r in intervention_records])

    matched_slope = _dlmo_slope_per_day(matched_dlmo_series)
    intervention_slope = _dlmo_slope_per_day(intervention_dlmo_series)
    slope_difference = (
        intervention_slope - matched_slope if matched_slope is not None and intervention_slope is not None else None
    )

    return InterventionEffectPhase2(
        intervention_id=intervention_id,
        participant_id=participant_id,
        match_quality=match,
        matched_mean_dlmo=matched_mean_dlmo,
        intervention_mean_dlmo=intervention_mean_dlmo,
        mean_dlmo_difference=_dlmo_change_minutes(matched_mean_dlmo, intervention_mean_dlmo),
        matched_slope_minutes_per_day=matched_slope,
        intervention_slope_minutes_per_day=intervention_slope,
        slope_difference=slope_difference,
        matched_mean_alignment=matched_mean_alignment,
        intervention_mean_alignment=intervention_mean_alignment,
        mean_alignment_difference=_alignment_change(matched_mean_alignment, intervention_mean_alignment),
        measurement_phase=2,
        interpretation=MATCHED_OBSERVATIONAL,
        sufficient_data=True,
    )

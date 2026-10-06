"""Period-level outcome aggregation: circular DLMO means/changes,
alignment means/changes, and the per-signal behavioral deltas
confound detection needs.

**DLMO and every clock-time signal use circular statistics
throughout** -- a plain ``recent_hour - baseline_hour`` would treat
23:55 -> 00:10 as a -23h45m change instead of the correct +15
minutes. This module is the one authoritative place period-level
circular aggregation happens for Phase 12.
"""

from __future__ import annotations

from typing import Optional, Sequence

from app.recommendations.catalogue import CLOCK_HOUR
from app.synthetic.time_utils import circular_diff_hours, circular_mean_hours

# Which of the five contributor signals are clock-time-valued (circular
# mean/diff) vs. plain-magnitude (linear mean/diff).
SIGNAL_VALUE_KIND = {
    "evening_screen": CLOCK_HOUR,
    "morning_light": "duration_minutes",
    "meal_timing": CLOCK_HOUR,
    "exercise": CLOCK_HOUR,
    "social_jetlag": "duration_minutes",
}


def _present(values: Sequence) -> list:
    return [v for v in values if v is not None]


def period_mean_dlmo_hour(dlmo_hours: Sequence) -> Optional[float]:
    present = _present(dlmo_hours)
    return circular_mean_hours(present) if present else None


def period_mean_alignment_score(scores: Sequence) -> Optional[float]:
    present = _present(scores)
    return sum(present) / len(present) if present else None


def dlmo_change_minutes(baseline_hour: Optional[float], recent_hour: Optional[float]) -> Optional[float]:
    """Signed change, recent relative to baseline, via the shortest
    circular arc -- positive = delay (later), negative = advance
    (earlier)."""

    if baseline_hour is None or recent_hour is None:
        return None
    return circular_diff_hours(recent_hour, baseline_hour) * 60.0


def alignment_change(baseline_score: Optional[float], recent_score: Optional[float]) -> Optional[float]:
    if baseline_score is None or recent_score is None:
        return None
    return recent_score - baseline_score


def signal_period_mean(signal: str, values: Sequence) -> Optional[float]:
    present = _present(values)
    if not present:
        return None
    if SIGNAL_VALUE_KIND[signal] == CLOCK_HOUR:
        return circular_mean_hours(present)
    return sum(present) / len(present)


def _signal_delta_minutes(signal: str, baseline_mean: Optional[float], intervention_mean: Optional[float]) -> Optional[float]:
    if baseline_mean is None or intervention_mean is None:
        return None
    if SIGNAL_VALUE_KIND[signal] == CLOCK_HOUR:
        return circular_diff_hours(intervention_mean, baseline_mean) * 60.0
    return intervention_mean - baseline_mean


def compute_all_signal_deltas(baseline_values_by_signal: dict, intervention_values_by_signal: dict) -> dict:
    """``{signal: values...}`` (raw per-day actual values, ``None`` for
    missing days) for both periods -> ``{signal: delta_minutes_or_None}``
    across all five behavioral signals -- used by confound detection."""

    deltas = {}
    for signal in SIGNAL_VALUE_KIND:
        baseline_mean = signal_period_mean(signal, baseline_values_by_signal.get(signal, []))
        intervention_mean = signal_period_mean(signal, intervention_values_by_signal.get(signal, []))
        deltas[signal] = _signal_delta_minutes(signal, baseline_mean, intervention_mean)
    return deltas

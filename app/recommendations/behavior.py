"""Resolves each candidate intervention's ``current_value`` from the
participant's recent behavioral window -- the same six-day window
Phase 9 already consumes, reused here rather than re-derived.

Only the five behaviors Phase 3/6/8/9 already track are supported:
evening screen duration, morning light duration, last-meal clock time,
exercise clock time, and social-jetlag minutes. An intervention whose
``target_behavior`` needs a signal this window does not carry (e.g.
caffeine timing -- not one of Phase 9's five ranked signals) simply
has no resolvable current value; the engine treats that as missing
data (see ``app.recommendations.engine``), never a fabricated 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

from app.synthetic.time_utils import add_hours


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _mean_of_present(values: Sequence) -> Optional[float]:
    present = [v for v in values if not _is_missing(v)]
    if not present:
        return None
    return sum(present) / len(present)


@dataclass(frozen=True)
class BehavioralHistory:
    """The six-day window of raw behavior, plus the single most recent
    sleep onset used to derive a screen-cutoff clock time."""

    actual_sleep_onset_hour: Optional[float]
    window_evening_screen_duration_hours: list = field(default_factory=list)
    window_morning_light_duration_minutes: list = field(default_factory=list)
    window_last_meal_hours: list = field(default_factory=list)
    window_exercise_hours: list = field(default_factory=list)
    window_social_jetlag_minutes: list = field(default_factory=list)


def resolve_current_value(signal: str, history: BehavioralHistory) -> Optional[float]:
    """The current-behavior value for one Phase 9 contributor signal, in
    the unit the matching catalogue entry's ``value_kind`` expects.

    ``evening_screen`` resolves to a **clock-time cutoff**
    (``sleep_onset - mean_screen_duration``), not the raw duration --
    this lets the primary-intervention template read naturally as
    "stop screens by {target_time}" (matching the worked example in
    ``docs/recommendation_engine.md``) while the underlying tracked
    quantity stays the duration Phase 6/8/9 already use.
    """

    if signal == "evening_screen":
        mean_duration = _mean_of_present(history.window_evening_screen_duration_hours)
        if mean_duration is None or history.actual_sleep_onset_hour is None:
            return None
        return add_hours(history.actual_sleep_onset_hour, -mean_duration)
    if signal == "morning_light":
        return _mean_of_present(history.window_morning_light_duration_minutes)
    if signal == "meal_timing":
        return _mean_of_present(history.window_last_meal_hours)
    if signal == "exercise":
        return _mean_of_present(history.window_exercise_hours)
    if signal == "social_jetlag":
        return _mean_of_present(history.window_social_jetlag_minutes)
    return None

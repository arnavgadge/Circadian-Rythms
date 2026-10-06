"""Resolves the single-day actual behavior value compliance is measured
against.

Deliberately separate from ``app.recommendations.behavior``: that
module resolves the **six-day window mean** an intervention was
*selected* from; this module resolves **one day's own value**, the
grain compliance tracking needs ("did you comply *today*"), which is
a different computation, not a duplicate of it.
"""

from __future__ import annotations

from typing import Optional

from app.database.models import DailyObservation
from app.synthetic.time_utils import add_hours, clock_time_to_hour


def resolve_actual_value(
    signal: str, observation: Optional[DailyObservation], actual_sleep_onset_hour: Optional[float]
) -> Optional[float]:
    if observation is None:
        return None

    if signal == "evening_screen":
        if observation.evening_screen_duration_minutes is None or actual_sleep_onset_hour is None:
            return None
        return add_hours(actual_sleep_onset_hour, -(observation.evening_screen_duration_minutes / 60.0))
    if signal == "morning_light":
        return observation.morning_light_duration_minutes
    if signal == "meal_timing":
        return clock_time_to_hour(observation.last_meal_time) if observation.last_meal_time is not None else None
    if signal == "exercise":
        return clock_time_to_hour(observation.exercise_time) if observation.exercise_time is not None else None
    if signal == "social_jetlag":
        # Only observable on free days by construction (Phase 3/4) --
        # None here is a missing observation, not zero jetlag.
        return observation.social_jetlag_minutes
    if signal == "caffeine":
        return clock_time_to_hour(observation.last_caffeine_time) if observation.last_caffeine_time is not None else None
    return None

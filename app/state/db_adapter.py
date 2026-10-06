"""Read-side adapters between the Phase 2 database and the state engine.

The state engine never queries the database itself (it is a pure
computation library); these small adapter functions translate the
existing ORM rows into the engine's own types, so a future production
inference pipeline (Phase 7+) is not left to invent that translation
from scratch, and so this phase can demonstrate "database
compatibility" without redesigning any schema.

Only reads are implemented here. Writing the final daily circadian
result belongs to the fusion layer (Phase 7), which is what actually
owns producing the authoritative ``circadian_labels`` row for a given
day; this phase does not write to the database.
"""

from __future__ import annotations

from typing import Optional

from app.database.models import DailyObservation, ParticipantProfile
from app.state.behavioral_effect import DailyBehaviorInputs
from app.state.circadian_state import CircadianState, ParticipantPhaseTraits
from app.synthetic.time_utils import clock_time_to_hour


def traits_from_participant_profile(
    profile: ParticipantProfile,
    baseline_sleep_onset_hour: float,
    light_sensitivity: float = 1.0,
    screen_sensitivity: float = 1.0,
    meal_sensitivity: float = 1.0,
) -> ParticipantPhaseTraits:
    """Build engine traits from a ``participant_profiles`` row.

    ``baseline_sleep_onset_hour`` and the sensitivity multipliers are
    not columns on ``participant_profiles`` (they are synthetic-generation
    concepts recorded in Phase 3's ``synthetic_personality_profile`` JSON
    blob, not part of the Phase 2 schema's core fields) -- callers that
    have them (e.g. by reading that JSON blob) pass them through
    explicitly; this function does not silently invent a default.
    """

    if profile.intrinsic_dlmo_time is None:
        raise ValueError("participant_profiles.intrinsic_dlmo_time is required to build ParticipantPhaseTraits")

    return ParticipantPhaseTraits(
        intrinsic_dlmo_hour=clock_time_to_hour(profile.intrinsic_dlmo_time),
        baseline_sleep_onset_hour=baseline_sleep_onset_hour,
        light_sensitivity=light_sensitivity,
        screen_sensitivity=screen_sensitivity,
        meal_sensitivity=meal_sensitivity,
        chronotype=profile.chronotype_category,
    )


def state_from_participant_profile(profile: ParticipantProfile) -> CircadianState:
    """Build the current :class:`CircadianState` from a ``participant_profiles`` row.

    Requires ``intrinsic_dlmo_time``, ``adapted_dlmo_time``, and
    ``current_dlmo_time`` to already be populated (i.e. the participant
    has been through at least one prior state update).
    """

    missing = [
        name
        for name, value in (
            ("intrinsic_dlmo_time", profile.intrinsic_dlmo_time),
            ("adapted_dlmo_time", profile.adapted_dlmo_time),
            ("current_dlmo_time", profile.current_dlmo_time),
        )
        if value is None
    ]
    if missing:
        raise ValueError(f"participant_profiles is missing required field(s) for state reconstruction: {missing}")

    return CircadianState(
        intrinsic_dlmo_hour=clock_time_to_hour(profile.intrinsic_dlmo_time),
        adapted_dlmo_hour=clock_time_to_hour(profile.adapted_dlmo_time),
        current_dlmo_hour=clock_time_to_hour(profile.current_dlmo_time),
        chronotype=profile.chronotype_category,
    )


def behavior_inputs_from_daily_observation(observation: DailyObservation) -> Optional[DailyBehaviorInputs]:
    """Build :class:`DailyBehaviorInputs` from a ``daily_observations`` row.

    Returns ``None`` if any of the five required raw signals is missing
    for that day -- callers are expected to apply their own missing-data
    policy (see Phase 4's imputation approach) rather than have this
    adapter silently fabricate a value.
    """

    required = (
        observation.morning_light_duration_minutes,
        observation.evening_screen_duration_minutes,
        observation.last_meal_time,
        observation.exercise_time,
        observation.last_caffeine_time,
        observation.caffeine_amount_mg,
    )
    if any(v is None for v in required):
        return None

    return DailyBehaviorInputs(
        morning_light_duration_minutes=observation.morning_light_duration_minutes,
        evening_screen_duration_hours=observation.evening_screen_duration_minutes / 60.0,
        last_meal_hour=clock_time_to_hour(observation.last_meal_time),
        exercise_hour=clock_time_to_hour(observation.exercise_time),
        caffeine_hour=clock_time_to_hour(observation.last_caffeine_time),
        caffeine_amount_mg=observation.caffeine_amount_mg,
    )

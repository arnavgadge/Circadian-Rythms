"""Tests for the state engine's read-side database adapters (Phase 2
schema compatibility) -- against a real small Phase 3 synthetic dataset.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.database.models import DailyObservation, Participant, ParticipantProfile
from app.state.db_adapter import behavior_inputs_from_daily_observation, state_from_participant_profile
from app.state.engine import step


def _first_participant_id(session) -> int:
    return session.execute(select(Participant.id).order_by(Participant.id)).scalars().first()


def test_state_from_participant_profile_reads_the_three_layers(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    profile = small_synthetic_session.get(ParticipantProfile, pid)

    state = state_from_participant_profile(profile)
    assert 0.0 <= state.intrinsic_dlmo_hour < 24.0
    assert 0.0 <= state.adapted_dlmo_hour < 24.0
    assert 0.0 <= state.current_dlmo_hour < 24.0
    assert state.chronotype == profile.chronotype_category


def test_state_from_participant_profile_requires_populated_fields(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    profile = small_synthetic_session.get(ParticipantProfile, pid)
    profile.adapted_dlmo_time = None

    with pytest.raises(ValueError):
        state_from_participant_profile(profile)


def test_behavior_inputs_from_daily_observation_reads_all_five_signals(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    obs = small_synthetic_session.execute(
        select(DailyObservation).where(DailyObservation.participant_id == pid).order_by(DailyObservation.observation_date)
    ).scalars().first()

    inputs = behavior_inputs_from_daily_observation(obs)
    assert inputs is not None
    assert inputs.morning_light_duration_minutes >= 0.0
    assert inputs.evening_screen_duration_hours >= 0.0
    assert 0.0 <= inputs.last_meal_hour < 24.0
    assert 0.0 <= inputs.exercise_hour < 24.0
    assert 0.0 <= inputs.caffeine_hour < 24.0
    assert inputs.caffeine_amount_mg >= 0.0


def test_behavior_inputs_from_daily_observation_returns_none_when_incomplete(small_synthetic_session):
    pid = _first_participant_id(small_synthetic_session)
    obs = small_synthetic_session.execute(
        select(DailyObservation).where(DailyObservation.participant_id == pid).order_by(DailyObservation.observation_date)
    ).scalars().first()
    obs.exercise_time = None

    assert behavior_inputs_from_daily_observation(obs) is None


def test_db_backed_state_and_behavior_can_drive_one_engine_step(small_synthetic_session):
    """End-to-end database compatibility check: read a real state and a
    real day of behavior straight from the Phase 2 schema and advance
    the engine by one day, with no special-casing required."""

    from app.state.circadian_state import ParticipantPhaseTraits

    pid = _first_participant_id(small_synthetic_session)
    profile = small_synthetic_session.get(ParticipantProfile, pid)
    obs = small_synthetic_session.execute(
        select(DailyObservation).where(DailyObservation.participant_id == pid).order_by(DailyObservation.observation_date)
    ).scalars().first()

    state = state_from_participant_profile(profile)
    behavior = behavior_inputs_from_daily_observation(obs)
    assert behavior is not None

    personality = profile.synthetic_personality_profile or {}
    traits = ParticipantPhaseTraits(
        intrinsic_dlmo_hour=state.intrinsic_dlmo_hour,
        baseline_sleep_onset_hour=state.intrinsic_dlmo_hour + 2.0,  # a plausible stand-in, not read from DB
        light_sensitivity=personality.get("light_sensitivity", 1.0),
        screen_sensitivity=personality.get("screen_sensitivity", 1.0),
        meal_sensitivity=personality.get("meal_sensitivity", 1.0),
    )

    new_state, debug = step(state, behavior, traits)
    assert 0.0 <= new_state.current_dlmo_hour < 24.0
    assert new_state.intrinsic_dlmo_hour == state.intrinsic_dlmo_hour

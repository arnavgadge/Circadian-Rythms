"""Tests for the stateful DLMO update engine."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from app.synthetic.behavior import generate_daily_behavior
from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC
from app.synthetic.dlmo_state import DLMOState, step
from app.synthetic.personalities import PERSONALITY_PROFILES
from app.synthetic.population import generate_participants
from app.synthetic.rng import RandomStreams
from app.synthetic.time_utils import circular_diff_hours


def _make_participant(seed=1):
    streams = RandomStreams(seed=seed)
    return generate_participants(1, streams, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)[0]


def _make_behavior(participant, day_index=0, seed=1):
    streams = RandomStreams(seed=seed)
    personality = PERSONALITY_PROFILES[participant.personality_key]
    return generate_daily_behavior(
        participant=participant,
        personality=personality,
        day_index=day_index,
        date_obj=date(2026, 1, 5 + day_index),
        behavior_rng=streams.participant_stream(0, "behavior"),
        disruption_rng=streams.participant_stream(0, "disruption"),
        physiology_rng=streams.participant_stream(0, "physiology"),
        synthetic=DEFAULT_SYNTHETIC,
        previous_sleep_midpoint_hour=None,
    )


def test_state_update_depends_on_previous_state_not_just_behavior():
    """Two runs with the same day-2 behavior but different day-1 endpoints
    must produce different day-2 states -- proving the state is carried
    forward sequentially rather than recomputed fresh each day."""

    participant = _make_participant()
    behavior = _make_behavior(participant)
    rng = np.random.default_rng(123)

    state_a = DLMOState(intrinsic_hour=21.0, adapted_hour=21.0, current_hour=20.0)
    state_b = DLMOState(intrinsic_hour=21.0, adapted_hour=21.0, current_hour=23.0)

    next_a, _ = step(state_a, behavior, participant, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, rng)
    next_b, _ = step(state_b, behavior, participant, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, rng)

    assert next_a.current_hour != pytest.approx(next_b.current_hour, abs=0.01)


def test_current_dlmo_stays_within_configured_bound_of_intrinsic():
    participant = _make_participant(seed=5)
    personality = PERSONALITY_PROFILES[participant.personality_key]
    streams = RandomStreams(seed=5)
    state = DLMOState(
        intrinsic_hour=participant.intrinsic_dlmo_hour,
        adapted_hour=participant.initial_adapted_dlmo_hour,
        current_hour=participant.initial_current_dlmo_hour,
    )
    behavior_rng = streams.participant_stream(0, "behavior")
    disruption_rng = streams.participant_stream(0, "disruption")
    physiology_rng = streams.participant_stream(0, "physiology")
    state_rng = streams.participant_stream(0, "state")

    previous_midpoint = None
    for day_index in range(60):  # run well beyond 30 days to stress the bound
        behavior = generate_daily_behavior(
            participant=participant,
            personality=personality,
            day_index=day_index,
            date_obj=date(2026, 1, 1) + timedelta(days=day_index),
            behavior_rng=behavior_rng,
            disruption_rng=disruption_rng,
            physiology_rng=physiology_rng,
            synthetic=DEFAULT_SYNTHETIC,
            previous_sleep_midpoint_hour=previous_midpoint,
        )
        state, _ = step(state, behavior, participant, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, state_rng)
        previous_midpoint = behavior.sleep_midpoint_hour

        current_diff = abs(circular_diff_hours(state.current_hour, state.intrinsic_hour))
        adapted_diff = abs(circular_diff_hours(state.adapted_hour, state.intrinsic_hour))
        assert current_diff <= DEFAULT_SYNTHETIC.current_bound_hours_from_intrinsic + 0.05
        assert adapted_diff <= DEFAULT_SYNTHETIC.adapted_bound_hours_from_intrinsic + 0.05


def test_single_day_state_change_is_bounded_by_clip_plus_slack():
    """A coding error that re-randomized the state each day would produce
    jumps comparable to a full circadian cycle; the real update should
    never move further than the daily clip plus the small pull/noise terms."""

    participant = _make_participant(seed=8)
    behavior = _make_behavior(participant, seed=8)
    rng = np.random.default_rng(1)
    state = DLMOState(
        intrinsic_hour=participant.intrinsic_dlmo_hour,
        adapted_hour=participant.initial_adapted_dlmo_hour,
        current_hour=participant.initial_current_dlmo_hour,
    )
    new_state, _ = step(state, behavior, participant, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, rng)

    change = abs(circular_diff_hours(new_state.current_hour, state.current_hour))
    max_clip_hours = max(abs(b) for b in DEFAULT_SYNTHETIC.daily_shift_clip_minutes) / 60.0
    safety_margin_hours = 1.0  # pull-to-adapted + state noise terms
    assert change <= max_clip_hours + safety_margin_hours

"""Tests for trajectory replay: stable/disruptive/chronotype scenarios,
and equivalence with the Phase 3 synthetic generator.
"""

from __future__ import annotations

import pytest

from app.state.behavioral_effect import DailyBehaviorInputs
from app.state.circadian_state import ParticipantPhaseTraits
from app.state.config import StateEngineConfig
from app.state.engine import initialize_state, step
from app.state.replay import replay_trajectory
from app.synthetic.time_utils import circular_diff_hours

_NEUTRAL = DailyBehaviorInputs(
    morning_light_duration_minutes=25.0, evening_screen_duration_hours=1.5,
    last_meal_hour=20.0, exercise_hour=8.0, caffeine_hour=9.0, caffeine_amount_mg=80.0,
)
_DISRUPTIVE = DailyBehaviorInputs(
    morning_light_duration_minutes=5.0, evening_screen_duration_hours=4.5,
    last_meal_hour=23.5, exercise_hour=21.0, caffeine_hour=14.0, caffeine_amount_mg=160.0,
)


# --- 11. Stable behavior ---

def test_stable_behavior_produces_a_settling_trajectory():
    traits = ParticipantPhaseTraits(intrinsic_dlmo_hour=21.5, baseline_sleep_onset_hour=23.5)
    days = replay_trajectory(traits, [_NEUTRAL] * 30)
    current = [d.state.current_dlmo_hour for d in days]

    late_changes = [abs(circular_diff_hours(current[i], current[i - 1])) for i in range(20, 30)]
    early_changes = [abs(circular_diff_hours(current[i], current[i - 1])) for i in range(1, 10)]
    # Under sustained constant behavior, day-to-day change should shrink
    # as the state approaches its equilibrium.
    assert sum(late_changes) <= sum(early_changes) + 1e-6


# --- 12. Persistent disruptive behavior ---

def test_persistent_disruptive_behavior_pushes_state_away_from_intrinsic():
    traits = ParticipantPhaseTraits(intrinsic_dlmo_hour=21.5, baseline_sleep_onset_hour=23.5)
    days = replay_trajectory(traits, [_DISRUPTIVE] * 30)
    final_distance = abs(circular_diff_hours(days[-1].state.current_dlmo_hour, 21.5))
    assert final_distance > 0.5  # meaningfully displaced from intrinsic


# --- 13. Recovery after disruption ---

def test_recovery_after_disruption_reduces_distance_from_intrinsic():
    traits = ParticipantPhaseTraits(intrinsic_dlmo_hour=21.5, baseline_sleep_onset_hour=23.5)
    disrupted_days = replay_trajectory(traits, [_DISRUPTIVE] * 15)
    peak_distance = max(abs(circular_diff_hours(d.state.current_dlmo_hour, 21.5)) for d in disrupted_days)

    recovery_days = replay_trajectory(traits, [_NEUTRAL] * 30, config=StateEngineConfig())
    # Continue recovery from the disrupted end-state rather than from scratch.
    state = disrupted_days[-1].state
    for _ in range(40):
        state, _ = step(state, _NEUTRAL, traits)
    final_distance = abs(circular_diff_hours(state.current_dlmo_hour, 21.5))

    assert final_distance < peak_distance


# --- 14. Chronotype differences ---

def test_different_intrinsic_chronotypes_produce_different_trajectories_under_identical_behavior():
    early_traits = ParticipantPhaseTraits(intrinsic_dlmo_hour=20.0, baseline_sleep_onset_hour=22.0, chronotype="Early")
    late_traits = ParticipantPhaseTraits(intrinsic_dlmo_hour=23.0, baseline_sleep_onset_hour=1.0, chronotype="Late")

    early_days = replay_trajectory(early_traits, [_NEUTRAL] * 15)
    late_days = replay_trajectory(late_traits, [_NEUTRAL] * 15)

    assert early_days[-1].state.current_dlmo_hour != pytest.approx(late_days[-1].state.current_dlmo_hour)
    # Each should stay anchored near its own intrinsic value, not converge to a shared one.
    assert abs(circular_diff_hours(early_days[-1].state.current_dlmo_hour, 20.0)) < 3.5
    assert abs(circular_diff_hours(late_days[-1].state.current_dlmo_hour, 23.0)) < 3.5


# --- Replay utility correctness ---

def test_replay_matches_manual_step_by_step_iteration():
    traits = ParticipantPhaseTraits(intrinsic_dlmo_hour=21.5, baseline_sleep_onset_hour=23.5)
    behaviors = [_NEUTRAL, _DISRUPTIVE, _NEUTRAL, _NEUTRAL, _DISRUPTIVE]

    replayed = replay_trajectory(traits, behaviors)

    state = initialize_state(traits.intrinsic_dlmo_hour, traits.chronotype)
    manual_states = []
    for behavior in behaviors:
        state, _ = step(state, behavior, traits)
        manual_states.append(state)

    for r, m in zip(replayed, manual_states):
        assert r.state == m


def test_replay_rejects_mismatched_dates_length():
    from datetime import date

    traits = ParticipantPhaseTraits(intrinsic_dlmo_hour=21.5, baseline_sleep_onset_hour=23.5)
    with pytest.raises(ValueError):
        replay_trajectory(traits, [_NEUTRAL, _NEUTRAL], dates=[date(2026, 1, 1)])


# --- 17. Replay equivalence with Phase 3 (noise-free controlled comparison) ---

def test_shared_engine_reproduces_phase3_generator_trajectory_when_noise_free():
    """With noise disabled, replaying a participant's actual generated
    behavior sequence through the standalone state engine must reproduce
    the exact trajectory the Phase 3 simulator itself produced -- proving
    both paths run through the same equations, not two implementations
    that happen to agree by coincidence.
    """

    from dataclasses import replace as dc_replace

    from app.state.circadian_state import ParticipantPhaseTraits as PhaseTraits
    from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SimulationRunConfig
    from app.synthetic.simulator import generate_synthetic_dataset

    noise_free_synthetic = dc_replace(
        DEFAULT_SYNTHETIC, day_level_noise_sd_minutes=0.0, daily_state_noise_sd_minutes=0.0
    )

    cfg = SimulationRunConfig(num_participants=3, num_days=15, seed=123)
    dataset = generate_synthetic_dataset(cfg, DEFAULT_SOURCE_BACKED, noise_free_synthetic)

    participant_row = dataset.participants_df.iloc[0]
    participant_days = dataset.daily_df[dataset.daily_df["participant_index"] == 0].sort_values("day_index")

    traits = PhaseTraits(
        intrinsic_dlmo_hour=participant_row["intrinsic_dlmo_hour"],
        baseline_sleep_onset_hour=participant_row["baseline_sleep_onset_hour"],
        light_sensitivity=participant_row["light_sensitivity"],
        screen_sensitivity=participant_row["screen_sensitivity"],
        meal_sensitivity=participant_row["meal_sensitivity"],
    )
    behaviors = [
        DailyBehaviorInputs(
            morning_light_duration_minutes=row["morning_light_duration_minutes"],
            evening_screen_duration_hours=row["evening_screen_duration_hours"],
            last_meal_hour=row["last_meal_hour"],
            exercise_hour=row["exercise_hour"],
            caffeine_hour=row["caffeine_hour"],
            caffeine_amount_mg=row["caffeine_amount_mg"],
        )
        for _, row in participant_days.iterrows()
    ]

    replay_config = StateEngineConfig(
        adaptation_rate=noise_free_synthetic.adapted_daily_pull_to_behavior_fraction,
        intrinsic_recovery_rate=noise_free_synthetic.adapted_daily_pull_to_intrinsic_fraction,
        adapted_max_offset_hours=noise_free_synthetic.adapted_bound_hours_from_intrinsic,
        current_pull_rate=noise_free_synthetic.current_daily_pull_to_adapted_fraction,
        current_max_offset_hours=noise_free_synthetic.current_bound_hours_from_intrinsic,
        daily_continuity_cap_minutes=None,
        initialization_offset_hours=participant_row["initial_adapted_dlmo_hour"] - participant_row["intrinsic_dlmo_hour"],
    )
    # The Phase 3 generator seeds current slightly differently from adapted
    # at onboarding (two independent small nudges); replicate that exactly
    # rather than assuming current == adapted at day zero.
    from app.state.circadian_state import CircadianState

    initial_state = CircadianState(
        intrinsic_dlmo_hour=participant_row["intrinsic_dlmo_hour"],
        adapted_dlmo_hour=participant_row["initial_adapted_dlmo_hour"],
        current_dlmo_hour=participant_row["initial_current_dlmo_hour"],
    )

    state = initial_state
    for behavior in behaviors:
        state, _ = step(
            state, behavior, traits, config=replay_config,
            source=DEFAULT_SOURCE_BACKED, synthetic=noise_free_synthetic, apply_continuity_cap=False,
        )

    generated_final_current = participant_days.iloc[-1]["current_dlmo_hour"]
    generated_final_adapted = participant_days.iloc[-1]["adapted_dlmo_hour"]

    assert state.current_dlmo_hour == pytest.approx(generated_final_current, abs=1e-9)
    assert state.adapted_dlmo_hour == pytest.approx(generated_final_adapted, abs=1e-9)

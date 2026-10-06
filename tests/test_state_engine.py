"""Tests for the core state-engine transition: initialization, the three
layers' update rules, bounds, continuity, and determinism."""

from __future__ import annotations

import sys

import numpy as np
import pytest

from app.state.behavioral_effect import DailyBehaviorInputs
from app.state.circadian_state import CircadianState, ParticipantPhaseTraits
from app.state.config import StateEngineConfig
from app.state.engine import initialize_state, initialize_state_stochastic, step, step_stochastic
from app.synthetic.time_utils import circular_diff_hours

_TRAITS = ParticipantPhaseTraits(intrinsic_dlmo_hour=21.5, baseline_sleep_onset_hour=23.5, chronotype="Intermediate")
# A moderate (not phase-neutral) behavior, used where the test only
# needs *some* ordinary day, not a zero-net-effect one.
_NEUTRAL_BEHAVIOR = DailyBehaviorInputs(
    morning_light_duration_minutes=20.0, evening_screen_duration_hours=2.0,
    last_meal_hour=20.5, exercise_hour=10.0, caffeine_hour=9.0, caffeine_amount_mg=90.0,
)
# A genuinely phase-neutral behavior (total_shift ~= 0 minutes): morning
# light right at the effect curve's zero-crossing (~9 min), no evening
# screen, an early meal, and exercise/caffeine inside their configured
# no-effect windows. Used specifically for the intrinsic-recovery check,
# which needs the *absence* of any behavioral pull to isolate the
# recovery-rate term.
_PHASE_NEUTRAL_BEHAVIOR = DailyBehaviorInputs(
    morning_light_duration_minutes=8.9, evening_screen_duration_hours=0.0,
    last_meal_hour=18.0, exercise_hour=14.0, caffeine_hour=10.0, caffeine_amount_mg=50.0,
)
_LATE_BEHAVIOR = DailyBehaviorInputs(
    morning_light_duration_minutes=5.0, evening_screen_duration_hours=4.5,
    last_meal_hour=23.5, exercise_hour=21.0, caffeine_hour=14.0, caffeine_amount_mg=160.0,
)


# --- 1. Initialization ---

def test_initialize_state_starts_coherent():
    state = initialize_state(21.5, chronotype="Intermediate")
    assert state.intrinsic_dlmo_hour == pytest.approx(21.5)
    assert state.adapted_dlmo_hour == pytest.approx(21.5)
    assert state.current_dlmo_hour == pytest.approx(state.adapted_dlmo_hour)
    assert state.chronotype == "Intermediate"


def test_initialize_state_with_offset():
    config = StateEngineConfig(initialization_offset_hours=0.2)
    state = initialize_state(21.5, config=config)
    assert state.adapted_dlmo_hour == pytest.approx(21.7)
    assert state.current_dlmo_hour == pytest.approx(21.7)


def test_initialize_state_stochastic_stays_close_to_intrinsic():
    rng = np.random.default_rng(1)
    state = initialize_state_stochastic(21.5, rng, chronotype="Intermediate")
    assert abs(circular_diff_hours(state.adapted_dlmo_hour, 21.5)) < 1.0
    assert abs(circular_diff_hours(state.current_dlmo_hour, 21.5)) < 1.0


# --- 2. Intrinsic immutability ---

def test_intrinsic_never_changes_across_steps():
    state = initialize_state(21.5)
    for _ in range(10):
        state, _ = step(state, _NEUTRAL_BEHAVIOR, _TRAITS)
        assert state.intrinsic_dlmo_hour == pytest.approx(21.5)


# --- 3 & 5. Adapted-state update / behavioral shift application ---

def test_adapted_moves_toward_persistent_behavior_direction():
    state = initialize_state(21.5)
    initial_adapted = state.adapted_dlmo_hour
    for _ in range(10):
        state, _ = step(state, _LATE_BEHAVIOR, _TRAITS)
    # Late-pulling behavior should have delayed (increased) adapted DLMO.
    assert circular_diff_hours(state.adapted_dlmo_hour, initial_adapted) > 0


def test_adapted_barely_moves_in_a_single_day():
    state = initialize_state(21.5)
    next_state, _ = step(state, _LATE_BEHAVIOR, _TRAITS)
    change = abs(circular_diff_hours(next_state.adapted_dlmo_hour, state.adapted_dlmo_hour))
    assert change < 0.1  # ~1%/day of a <=90min shift is only a few minutes


# --- 4. Current-state update ---

def test_current_responds_to_behavior_more_than_adapted_in_one_day():
    state = initialize_state(21.5)
    next_state, _ = step(state, _LATE_BEHAVIOR, _TRAITS)
    current_change = abs(circular_diff_hours(next_state.current_dlmo_hour, state.current_dlmo_hour))
    adapted_change = abs(circular_diff_hours(next_state.adapted_dlmo_hour, state.adapted_dlmo_hour))
    assert current_change > adapted_change


# --- 6. Intrinsic recovery ---

def test_adapted_recovers_toward_intrinsic_once_behavior_is_neutral():
    state = initialize_state(21.5)
    for _ in range(15):
        state, _ = step(state, _LATE_BEHAVIOR, _TRAITS)
    displaced_adapted = state.adapted_dlmo_hour

    for _ in range(60):
        state, _ = step(state, _PHASE_NEUTRAL_BEHAVIOR, _TRAITS)

    final_distance = abs(circular_diff_hours(state.adapted_dlmo_hour, 21.5))
    displaced_distance = abs(circular_diff_hours(displaced_adapted, 21.5))
    assert final_distance < displaced_distance


# --- 7. Adapted bounds ---

def test_adapted_stays_within_configured_bound():
    config = StateEngineConfig(adapted_max_offset_hours=2.0)
    state = initialize_state(21.5, config=config)
    for _ in range(200):
        state, _ = step(state, _LATE_BEHAVIOR, _TRAITS, config=config)
        assert abs(circular_diff_hours(state.adapted_dlmo_hour, 21.5)) <= 2.0 + 1e-6


# --- 8. Current bounds ---

def test_current_stays_within_configured_bound():
    config = StateEngineConfig(current_max_offset_hours=3.0)
    state = initialize_state(21.5, config=config)
    for _ in range(200):
        state, _ = step(state, _LATE_BEHAVIOR, _TRAITS, config=config)
        assert abs(circular_diff_hours(state.current_dlmo_hour, 21.5)) <= 3.0 + 1e-6


# --- 9. Continuity cap ---

def test_continuity_cap_limits_a_single_day_jump():
    config = StateEngineConfig(daily_continuity_cap_minutes=30.0, current_max_offset_hours=10.0)
    # A pathological previous state far from adapted forces a large
    # pull-to-adapted term that would otherwise exceed the cap.
    state = CircadianState(intrinsic_dlmo_hour=10.0, adapted_dlmo_hour=10.0, current_dlmo_hour=4.0)
    new_state, debug = step(state, _NEUTRAL_BEHAVIOR, _TRAITS, config=config)
    change = abs(circular_diff_hours(new_state.current_dlmo_hour, state.current_dlmo_hour))
    assert change <= 30.0 / 60.0 + 1e-6
    assert debug.continuity_cap_applied is True


def test_continuity_cap_disabled_allows_larger_jump():
    config = StateEngineConfig(daily_continuity_cap_minutes=30.0, current_max_offset_hours=10.0)
    state = CircadianState(intrinsic_dlmo_hour=10.0, adapted_dlmo_hour=10.0, current_dlmo_hour=4.0)
    _, debug = step(state, _NEUTRAL_BEHAVIOR, _TRAITS, config=config, apply_continuity_cap=False)
    assert debug.continuity_cap_applied is False


# --- 10. Midnight transition ---

def test_step_handles_a_state_straddling_midnight_correctly():
    from app.state.circadian_state import CircadianState

    state = CircadianState(intrinsic_dlmo_hour=23.9, adapted_dlmo_hour=23.9, current_dlmo_hour=23.95)
    new_state, _ = step(state, _NEUTRAL_BEHAVIOR, ParticipantPhaseTraits(intrinsic_dlmo_hour=23.9, baseline_sleep_onset_hour=1.5))
    # A small behavioral advance should be able to cross midnight without
    # an artificial jump: the change should be small in circular terms.
    change = circular_diff_hours(new_state.current_dlmo_hour, state.current_dlmo_hour)
    assert abs(change) < 2.0


# --- 15. Deterministic inference ---

def test_step_is_deterministic_given_same_inputs():
    state = initialize_state(21.5)
    state_a, _ = step(state, _NEUTRAL_BEHAVIOR, _TRAITS)
    state_b, _ = step(state, _NEUTRAL_BEHAVIOR, _TRAITS)
    assert state_a == state_b


def test_step_default_noise_is_zero_and_pure():
    state = initialize_state(21.5)
    results = [step(state, _NEUTRAL_BEHAVIOR, _TRAITS)[0] for _ in range(5)]
    assert len(set(results)) == 1


# --- 16. Explicit stochastic simulation mode ---

def test_step_stochastic_produces_varying_results_across_calls():
    state = initialize_state(21.5)
    rng = np.random.default_rng(0)
    outcomes = {step_stochastic(state, _NEUTRAL_BEHAVIOR, _TRAITS, rng)[0].current_dlmo_hour for _ in range(5)}
    assert len(outcomes) > 1  # different draws should (almost certainly) differ


def test_step_stochastic_is_reproducible_with_same_rng_state():
    state = initialize_state(21.5)
    result_a, _ = step_stochastic(state, _NEUTRAL_BEHAVIOR, _TRAITS, np.random.default_rng(42))
    result_b, _ = step_stochastic(state, _NEUTRAL_BEHAVIOR, _TRAITS, np.random.default_rng(42))
    assert result_a == result_b


def test_randomness_is_never_hidden_in_the_deterministic_step_signature():
    import inspect

    sig = inspect.signature(step)
    assert "rng" not in sig.parameters
    assert "noise_minutes" in sig.parameters
    assert sig.parameters["noise_minutes"].default == 0.0


# --- 18. No XGBoost dependency ---

def test_state_package_has_no_xgboost_dependency():
    import app.state.behavioral_effect
    import app.state.circadian_state
    import app.state.config
    import app.state.diagnostics
    import app.state.engine
    import app.state.replay
    import app.state.sanity

    assert "xgboost" not in sys.modules or all(
        "app.state" not in mod for mod in sys.modules if "xgboost" in mod
    )
    for module in (
        app.state.engine, app.state.behavioral_effect, app.state.replay,
        app.state.sanity, app.state.config, app.state.circadian_state, app.state.diagnostics,
    ):
        source = inspect_source(module)
        assert "xgboost" not in source.lower()
        assert "app.models" not in source


def inspect_source(module) -> str:
    import inspect

    return inspect.getsource(module)

"""Tests for the automated state sanity-check suite itself."""

from __future__ import annotations

from app.state.behavioral_effect import DailyBehaviorInputs
from app.state.circadian_state import CircadianState, ParticipantPhaseTraits
from app.state.config import StateEngineConfig
from app.state.engine import initialize_state, step
from app.state.replay import replay_trajectory
from app.state.sanity import check_determinism, check_recovery_toward_equilibrium, validate_trajectory

_TRAITS = ParticipantPhaseTraits(intrinsic_dlmo_hour=21.5, baseline_sleep_onset_hour=23.5)
_NEUTRAL = DailyBehaviorInputs(
    morning_light_duration_minutes=20.0, evening_screen_duration_hours=2.0,
    last_meal_hour=20.5, exercise_hour=8.0, caffeine_hour=9.0, caffeine_amount_mg=90.0,
)
_DISRUPTIVE = DailyBehaviorInputs(
    morning_light_duration_minutes=5.0, evening_screen_duration_hours=4.5,
    last_meal_hour=23.5, exercise_hour=21.0, caffeine_hour=14.0, caffeine_amount_mg=160.0,
)


def test_validate_trajectory_passes_for_a_normal_run():
    days = replay_trajectory(_TRAITS, [_NEUTRAL] * 30)
    report = validate_trajectory(days)
    assert report.ok, report.summary_lines()
    assert len(report.checks) == 8


def test_validate_trajectory_detects_intrinsic_drift():
    days = replay_trajectory(_TRAITS, [_NEUTRAL] * 5)
    # Tamper with one day's intrinsic value to simulate a coding bug.
    tampered_state = CircadianState(
        intrinsic_dlmo_hour=days[2].state.intrinsic_dlmo_hour + 1.0,
        adapted_dlmo_hour=days[2].state.adapted_dlmo_hour,
        current_dlmo_hour=days[2].state.current_dlmo_hour,
    )
    days[2] = type(days[2])(date=days[2].date, state=tampered_state, debug=days[2].debug)

    report = validate_trajectory(days)
    check = next(c for c in report.checks if c.name == "intrinsic_never_changes")
    assert not check.passed


def test_validate_trajectory_detects_out_of_bound_adapted():
    config = StateEngineConfig(adapted_max_offset_hours=2.0)
    days = replay_trajectory(_TRAITS, [_NEUTRAL] * 3, config=config)
    tampered_state = CircadianState(
        intrinsic_dlmo_hour=days[0].state.intrinsic_dlmo_hour,
        adapted_dlmo_hour=days[0].state.intrinsic_dlmo_hour + 5.0,
        current_dlmo_hour=days[0].state.current_dlmo_hour,
    )
    days[0] = type(days[0])(date=days[0].date, state=tampered_state, debug=days[0].debug)

    report = validate_trajectory(days, config=config)
    check = next(c for c in report.checks if c.name == "adapted_within_bound")
    assert not check.passed


def test_check_recovery_toward_equilibrium_passes_for_a_normal_scenario():
    report = check_recovery_toward_equilibrium(_TRAITS, _DISRUPTIVE, _NEUTRAL)
    assert report.ok, report.summary_lines()


def test_check_determinism_passes():
    state = initialize_state(_TRAITS.intrinsic_dlmo_hour)
    report = check_determinism(state, _NEUTRAL, _TRAITS)
    assert report.ok


def test_raise_if_failed_raises_on_broken_trajectory():
    config = StateEngineConfig(adapted_max_offset_hours=2.0)
    days = replay_trajectory(_TRAITS, [_NEUTRAL] * 3, config=config)
    tampered_state = CircadianState(
        intrinsic_dlmo_hour=days[0].state.intrinsic_dlmo_hour,
        adapted_dlmo_hour=days[0].state.intrinsic_dlmo_hour + 5.0,
        current_dlmo_hour=days[0].state.current_dlmo_hour,
    )
    days[0] = type(days[0])(date=days[0].date, state=tampered_state, debug=days[0].debug)
    report = validate_trajectory(days, config=config)

    try:
        report.raise_if_failed()
        assert False, "expected AssertionError"
    except AssertionError:
        pass

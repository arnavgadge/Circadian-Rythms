"""AUDIT 7 -- State engine adversarial audit.

Runs 30/90/180-day synthetic trajectories through the *real* state
engine (``app.state.engine`` / ``app.state.replay``) and checks the
documented invariants:

- ``intrinsic_DLMO`` is immutable across the whole trajectory.
- ``adapted_DLMO`` stays within ``StateEngineConfig.adapted_max_offset_hours``
  (2.0h) of intrinsic.
- ``current_DLMO`` stays within ``StateEngineConfig.current_max_offset_hours``
  (3.0h) of intrinsic.
- No single-day change in ``current_DLMO`` exceeds
  ``StateEngineConfig.daily_continuity_cap_minutes`` (60 minutes).
- A persistent behavioral disturbance shifts state in the
  architecturally-expected direction (later, for late-light/late-sleep
  disturbance), and removing it lets state recover.
- No runaway drift, NaN/Inf, or growing-amplitude oscillation across a
  full 180-day run.
"""

from __future__ import annotations

import math

import pytest

from app.state.behavioral_effect import DailyBehaviorInputs
from app.state.circadian_state import ParticipantPhaseTraits
from app.state.config import DEFAULT_STATE_ENGINE_CONFIG
from app.state.replay import replay_trajectory
from app.synthetic.time_utils import circular_diff_hours

NEUTRAL = DailyBehaviorInputs(
    morning_light_duration_minutes=25.0, evening_screen_duration_hours=1.5,
    last_meal_hour=20.0, exercise_hour=8.0, caffeine_hour=9.0, caffeine_amount_mg=80.0,
)
# Persistent late light exposure + late sleep/meal/screen disturbance --
# architecturally expected to push DLMO *later* (positive circular delta).
LATE_DISTURBANCE = DailyBehaviorInputs(
    morning_light_duration_minutes=0.0, evening_screen_duration_hours=5.0,
    last_meal_hour=23.5, exercise_hour=22.0, caffeine_hour=16.0, caffeine_amount_mg=200.0,
)

CONFIG = DEFAULT_STATE_ENGINE_CONFIG


def _traits(intrinsic=21.5, baseline_sleep=23.5, chronotype=None):
    return ParticipantPhaseTraits(
        intrinsic_dlmo_hour=intrinsic, baseline_sleep_onset_hour=baseline_sleep, chronotype=chronotype
    )


@pytest.mark.parametrize("n_days", [30, 90, 180])
def test_intrinsic_dlmo_never_changes(n_days):
    traits = _traits()
    days = replay_trajectory(traits, [NEUTRAL] * n_days)
    for d in days:
        assert d.state.intrinsic_dlmo_hour == pytest.approx(traits.intrinsic_dlmo_hour)


@pytest.mark.parametrize("n_days", [30, 90, 180])
@pytest.mark.parametrize("behavior", [NEUTRAL, LATE_DISTURBANCE])
def test_adapted_dlmo_stays_within_documented_bound(n_days, behavior):
    traits = _traits()
    days = replay_trajectory(traits, [behavior] * n_days)
    bound = CONFIG.adapted_max_offset_hours
    for d in days:
        dist = abs(circular_diff_hours(d.state.adapted_dlmo_hour, d.state.intrinsic_dlmo_hour))
        assert dist <= bound + 1e-6, f"adapted_DLMO {dist}h from intrinsic exceeds bound {bound}h"


@pytest.mark.parametrize("n_days", [30, 90, 180])
@pytest.mark.parametrize("behavior", [NEUTRAL, LATE_DISTURBANCE])
def test_current_dlmo_stays_within_documented_bound(n_days, behavior):
    traits = _traits()
    days = replay_trajectory(traits, [behavior] * n_days)
    bound = CONFIG.current_max_offset_hours
    for d in days:
        dist = abs(circular_diff_hours(d.state.current_dlmo_hour, d.state.intrinsic_dlmo_hour))
        assert dist <= bound + 1e-6, f"current_DLMO {dist}h from intrinsic exceeds bound {bound}h"


@pytest.mark.parametrize("n_days", [30, 90, 180])
def test_no_single_day_jump_exceeds_continuity_cap(n_days):
    traits = _traits()
    days = replay_trajectory(traits, [LATE_DISTURBANCE] * n_days)  # worst case: sustained max disturbance
    cap_hours = CONFIG.daily_continuity_cap_minutes / 60.0

    prev_current = traits.intrinsic_dlmo_hour  # initial state's current == adapted == intrinsic (offset 0 by default)
    for d in days:
        jump = abs(circular_diff_hours(d.state.current_dlmo_hour, prev_current))
        assert jump <= cap_hours + 1e-6, f"day-over-day current_DLMO jump {jump * 60}min exceeds cap {CONFIG.daily_continuity_cap_minutes}min"
        prev_current = d.state.current_dlmo_hour


def test_persistent_late_disturbance_shifts_state_later():
    """Late light + late screen/meal/exercise/caffeine should push
    current_DLMO later (positive direction) relative to intrinsic --
    the architecturally-documented sign convention (positive minutes =
    phase delay)."""

    traits = _traits()
    days = replay_trajectory(traits, [LATE_DISTURBANCE] * 30)
    final_delta = circular_diff_hours(days[-1].state.current_dlmo_hour, traits.intrinsic_dlmo_hour)
    assert final_delta > 0.3, f"expected a later (positive) shift under late disturbance, got {final_delta}h"


def test_state_recovers_after_disturbance_is_removed():
    traits = _traits()
    disrupted = replay_trajectory(traits, [LATE_DISTURBANCE] * 20)
    peak_distance = abs(circular_diff_hours(disrupted[-1].state.current_dlmo_hour, traits.intrinsic_dlmo_hour))

    state = disrupted[-1].state
    from app.state.engine import step as engine_step
    distances = []
    for _ in range(60):
        state, _ = engine_step(state, NEUTRAL, traits)
        distances.append(abs(circular_diff_hours(state.current_dlmo_hour, traits.intrinsic_dlmo_hour)))

    assert distances[-1] < peak_distance, "state failed to recover toward intrinsic after disturbance removed"
    # Recovery should also not be stuck: later distances should generally
    # trend down relative to early recovery distances.
    assert sum(distances[-10:]) <= sum(distances[:10]) + 1e-6


def test_180_day_run_no_nan_or_inf_and_no_runaway_drift():
    traits = _traits()
    days = replay_trajectory(traits, [LATE_DISTURBANCE] * 180)
    for d in days:
        for value in (d.state.intrinsic_dlmo_hour, d.state.adapted_dlmo_hour, d.state.current_dlmo_hour):
            assert math.isfinite(value), f"non-finite state value encountered: {value}"
            assert 0.0 <= value < 24.0, f"state value {value} outside valid clock-hour range"

    # Runaway-drift check: since current is bounded to within
    # current_max_offset_hours of intrinsic at every step, the whole
    # trajectory must stay within that bound (already checked above per
    # value, but assert the aggregate too for a single clear signal).
    max_dist = max(
        abs(circular_diff_hours(d.state.current_dlmo_hour, traits.intrinsic_dlmo_hour)) for d in days
    )
    assert max_dist <= CONFIG.current_max_offset_hours + 1e-6


def test_180_day_run_no_growing_amplitude_oscillation_under_constant_input():
    """Under a *constant* daily behavior input, the trajectory should
    settle rather than oscillate with growing amplitude."""

    traits = _traits()
    days = replay_trajectory(traits, [LATE_DISTURBANCE] * 180)
    current = [d.state.current_dlmo_hour for d in days]
    deltas = [abs(circular_diff_hours(current[i], current[i - 1])) for i in range(1, len(current))]

    # Compare the mean magnitude of day-to-day change in the last third
    # of the run against the first third: it must not have grown.
    third = len(deltas) // 3
    first_third_mean = sum(deltas[:third]) / third
    last_third_mean = sum(deltas[-third:]) / third
    assert last_third_mean <= first_third_mean + 1e-3, (
        f"day-to-day oscillation amplitude grew over the run: "
        f"first third mean={first_third_mean}, last third mean={last_third_mean}"
    )

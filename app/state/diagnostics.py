"""Diagnostic plots for the state engine.

Self-contained: builds its own small set of illustrative example
participants and behavior patterns (no database dependency), runs them
through the deterministic :func:`app.state.engine.step` path, and plots
the resulting trajectories. Research diagnostics only, not UI.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from app.state.behavioral_effect import DailyBehaviorInputs
from app.state.circadian_state import ParticipantPhaseTraits
from app.state.config import DEFAULT_STATE_ENGINE_CONFIG
from app.state.engine import initialize_state, step
from app.synthetic.time_utils import circular_diff_hours

_DAYS = 30


def _constant_behavior(**kwargs) -> DailyBehaviorInputs:
    return DailyBehaviorInputs(**kwargs)


_EXAMPLE_BEHAVIORS = {
    "stable_early": _constant_behavior(
        morning_light_duration_minutes=35.0, evening_screen_duration_hours=1.0,
        last_meal_hour=19.5, exercise_hour=7.0, caffeine_hour=8.0, caffeine_amount_mg=80.0,
    ),
    "stable_late": _constant_behavior(
        morning_light_duration_minutes=10.0, evening_screen_duration_hours=3.0,
        last_meal_hour=23.0, exercise_hour=19.0, caffeine_hour=13.0, caffeine_amount_mg=140.0,
    ),
    "screen_heavy": _constant_behavior(
        morning_light_duration_minutes=15.0, evening_screen_duration_hours=4.5,
        last_meal_hour=21.0, exercise_hour=18.0, caffeine_hour=11.0, caffeine_amount_mg=100.0,
    ),
}

_WEEKDAY_BEHAVIOR = _constant_behavior(
    morning_light_duration_minutes=15.0, evening_screen_duration_hours=2.0,
    last_meal_hour=21.0, exercise_hour=17.0, caffeine_hour=11.0, caffeine_amount_mg=110.0,
)
_WEEKEND_BEHAVIOR = _constant_behavior(
    morning_light_duration_minutes=5.0, evening_screen_duration_hours=3.5,
    last_meal_hour=23.5, exercise_hour=19.0, caffeine_hour=13.0, caffeine_amount_mg=110.0,
)

_TRAITS = ParticipantPhaseTraits(intrinsic_dlmo_hour=21.5, baseline_sleep_onset_hour=23.5, chronotype="Intermediate")


def _run_trajectory(behaviors: list) -> tuple:
    state = initialize_state(_TRAITS.intrinsic_dlmo_hour, _TRAITS.chronotype)
    states, debugs = [], []
    for behavior in behaviors:
        state, debug = step(state, behavior, _TRAITS)
        states.append(state)
        debugs.append(debug)
    return states, debugs


def _unwrap_hours(values: np.ndarray) -> np.ndarray:
    unwrapped = values.copy().astype(float)
    for i in range(1, len(unwrapped)):
        while unwrapped[i] - unwrapped[i - 1] > 12.0:
            unwrapped[i] -= 24.0
        while unwrapped[i] - unwrapped[i - 1] < -12.0:
            unwrapped[i] += 24.0
    return unwrapped


def build_diagnostics_plots(output_dir: Path) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    written = {}

    # --- 1. Intrinsic vs adapted vs current, for the five example profiles ---
    social_jetlag_behaviors = [
        _WEEKEND_BEHAVIOR if (day % 7) in (5, 6) else _WEEKDAY_BEHAVIOR for day in range(_DAYS)
    ]
    chaotic_rng = np.random.default_rng(7)
    chaotic_behaviors = [
        DailyBehaviorInputs(
            morning_light_duration_minutes=max(0.0, chaotic_rng.normal(15, 15)),
            evening_screen_duration_hours=max(0.0, chaotic_rng.normal(2.5, 1.5)),
            last_meal_hour=(chaotic_rng.normal(21, 2)) % 24,
            exercise_hour=(chaotic_rng.normal(17, 5)) % 24,
            caffeine_hour=(chaotic_rng.normal(11, 3)) % 24,
            caffeine_amount_mg=max(0.0, chaotic_rng.normal(100, 40)),
        )
        for _ in range(_DAYS)
    ]

    profiles = {
        "stable_early": [_EXAMPLE_BEHAVIORS["stable_early"]] * _DAYS,
        "stable_late": [_EXAMPLE_BEHAVIORS["stable_late"]] * _DAYS,
        "screen_heavy": [_EXAMPLE_BEHAVIORS["screen_heavy"]] * _DAYS,
        "social_jetlag": social_jetlag_behaviors,
        "chaotic": chaotic_behaviors,
    }

    fig, axes = plt.subplots(5, 1, figsize=(9, 16), sharex=True)
    for ax, (name, behaviors) in zip(axes, profiles.items()):
        states, _ = _run_trajectory(behaviors)
        days = np.arange(1, _DAYS + 1)
        intrinsic = np.array([s.intrinsic_dlmo_hour for s in states])
        adapted = _unwrap_hours(np.array([s.adapted_dlmo_hour for s in states]))
        current = _unwrap_hours(np.array([s.current_dlmo_hour for s in states]))
        # unwrap adapted/current relative to intrinsic's own reference for readable plotting
        ax.plot(days, [intrinsic[0]] * _DAYS, label="intrinsic", linestyle="--", color="black")
        ax.plot(days, adapted, label="adapted", color="tab:orange")
        ax.plot(days, current, label="current", color="tab:blue")
        ax.set_title(name)
        ax.set_ylabel("DLMO (hour)")
        ax.legend(fontsize=7, loc="upper right")
    axes[-1].set_xlabel("Day")
    fig.suptitle("Intrinsic vs. adapted vs. current DLMO over 30 days")
    fig.tight_layout()
    path = output_dir / "01_three_layer_trajectories.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["three_layer_trajectories"] = path

    # --- 2 & 3. Persistent disruption then recovery ---
    disruptive = _EXAMPLE_BEHAVIORS["stable_late"]
    normal = _EXAMPLE_BEHAVIORS["stable_early"]
    behaviors = [disruptive] * 12 + [normal] * 18
    states, debugs = _run_trajectory(behaviors)
    days = np.arange(1, len(behaviors) + 1)
    intrinsic = states[0].intrinsic_dlmo_hour
    adapted = _unwrap_hours(np.array([s.adapted_dlmo_hour for s in states]))
    current = _unwrap_hours(np.array([s.current_dlmo_hour for s in states]))

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.axvline(12.5, color="gray", linestyle=":", label="behavior normalizes")
    ax.axhline(intrinsic, color="black", linestyle="--", linewidth=1, label="intrinsic")
    ax.plot(days, adapted, label="adapted", color="tab:orange")
    ax.plot(days, current, label="current", color="tab:blue")
    ax.set_xlabel("Day")
    ax.set_ylabel("DLMO (hour)")
    ax.set_title("Disruption (12 days of late-type behavior) then recovery (18 days of early-type behavior)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = output_dir / "02_disruption_and_recovery.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["disruption_and_recovery"] = path

    # --- 4. Current DLMO daily continuity (day-over-day change magnitude) ---
    states_sh, _ = _run_trajectory(profiles["screen_heavy"])
    current_sh = [s.current_dlmo_hour for s in states_sh]
    jumps = [
        abs(circular_diff_hours(current_sh[i], current_sh[i - 1])) * 60.0 for i in range(1, len(current_sh))
    ]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(range(2, len(current_sh) + 1), jumps, color="tab:green")
    ax.axhline(
        DEFAULT_STATE_ENGINE_CONFIG.daily_continuity_cap_minutes, color="red", linestyle="--",
        label=f"continuity cap ({DEFAULT_STATE_ENGINE_CONFIG.daily_continuity_cap_minutes:.0f} min)",
    )
    ax.set_xlabel("Day")
    ax.set_ylabel("|day-over-day current DLMO change| (minutes)")
    ax.set_title("Current DLMO daily continuity (screen-heavy profile)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = output_dir / "03_daily_continuity.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["daily_continuity"] = path

    # --- 5. Behavior-driven shifts alongside the resulting trajectory ---
    states_sj, debugs_sj = _run_trajectory(social_jetlag_behaviors)
    shifts = [d.behavioral_effect.total_shift for d in debugs_sj]
    current_sj = _unwrap_hours(np.array([s.current_dlmo_hour for s in states_sj]))
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
    ax1.bar(range(1, _DAYS + 1), shifts, color="tab:purple")
    ax1.set_ylabel("Behavioral shift (min/day)")
    ax1.set_title("Behavior-driven shifts and resulting current DLMO (social-jetlag profile)")
    ax2.plot(range(1, _DAYS + 1), current_sj, color="tab:blue")
    ax2.set_ylabel("Current DLMO (hour)")
    ax2.set_xlabel("Day")
    fig.tight_layout()
    path = output_dir / "04_behavior_driven_shifts.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["behavior_driven_shifts"] = path

    # --- 6. Effect of midnight crossings ---
    # An intrinsic anchor right at the wrap boundary (23:54), alternating
    # every 5 days between an earlier- and later-pulling behavior, so the
    # trajectory genuinely oscillates back and forth across midnight --
    # a naive [0, 24) plot will show real vertical "cliffs" here.
    late_traits = ParticipantPhaseTraits(intrinsic_dlmo_hour=23.9, baseline_sleep_onset_hour=1.5, chronotype="Late")
    earlier_pull_behavior = _EXAMPLE_BEHAVIORS["stable_early"]
    later_pull_behavior = _EXAMPLE_BEHAVIORS["stable_late"]
    oscillating_behaviors = [
        later_pull_behavior if (day // 5) % 2 == 0 else earlier_pull_behavior for day in range(_DAYS)
    ]

    state = initialize_state(late_traits.intrinsic_dlmo_hour, late_traits.chronotype)
    raw_hours = []
    for behavior in oscillating_behaviors:
        state, _ = step(state, behavior, late_traits)
        raw_hours.append(state.current_dlmo_hour)
    unwrapped_hours = _unwrap_hours(np.array(raw_hours))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.plot(range(1, _DAYS + 1), raw_hours, marker="o", markersize=3, color="tab:red")
    ax1.set_title("Naive plot (raw [0,24) hours) -- midnight looks like a cliff")
    ax1.set_xlabel("Day")
    ax1.set_ylabel("Current DLMO (hour, raw)")
    ax2.plot(range(1, _DAYS + 1), unwrapped_hours, marker="o", markersize=3, color="tab:blue")
    ax2.set_title("Unwrapped plot -- the same trajectory, continuous across midnight")
    ax2.set_xlabel("Day")
    ax2.set_ylabel("Current DLMO (hour, unwrapped)")
    fig.suptitle("Effect of midnight crossings on trajectory visualization (late-chronotype example)")
    fig.tight_layout()
    path = output_dir / "05_midnight_crossings.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    written["midnight_crossings"] = path

    return written

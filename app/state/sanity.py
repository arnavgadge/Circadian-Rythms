"""Automated state sanity checks.

Implements the 10 checks required for Phase 6. These verify the state
*engine* behaves as designed -- not a claim about real human circadian
biology.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.state.behavioral_effect import DailyBehaviorInputs
from app.state.circadian_state import ParticipantPhaseTraits
from app.state.config import DEFAULT_STATE_ENGINE_CONFIG, StateEngineConfig
from app.state.engine import initialize_state, step
from app.state.replay import ReplayDay
from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SourceBackedAssumptions, SyntheticAssumptions
from app.synthetic.time_utils import circular_diff_hours


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class ValidationReport:
    checks: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append(CheckResult(name=name, passed=bool(passed), detail=detail))

    def summary_lines(self) -> list:
        return [f"[{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.detail}" for c in self.checks]

    def raise_if_failed(self) -> None:
        failed = [c for c in self.checks if not c.passed]
        if failed:
            raise AssertionError("State trajectory failed validation: " + "; ".join(f"{c.name} ({c.detail})" for c in failed))


def validate_trajectory(
    replay_days: list, config: StateEngineConfig = DEFAULT_STATE_ENGINE_CONFIG
) -> ValidationReport:
    """Checks 1-5, 7-9 of the Phase 6 "STATE SANITY CHECKS" list, run
    against one participant's replayed trajectory."""

    report = ValidationReport()
    if not replay_days:
        report.add("non_empty_trajectory", False, "no days to validate")
        return report

    intrinsic = replay_days[0].state.intrinsic_dlmo_hour

    # 1. intrinsic_DLMO never changes
    intrinsic_values = {d.state.intrinsic_dlmo_hour for d in replay_days}
    report.add(
        "intrinsic_never_changes",
        len(intrinsic_values) == 1,
        f"observed {len(intrinsic_values)} distinct intrinsic values" if len(intrinsic_values) != 1 else "constant",
    )

    # 2. adapted_DLMO remains within configured bound
    adapted_diffs = [abs(circular_diff_hours(d.state.adapted_dlmo_hour, intrinsic)) for d in replay_days]
    max_adapted_diff = max(adapted_diffs)
    report.add(
        "adapted_within_bound",
        max_adapted_diff <= config.adapted_max_offset_hours + 1e-6,
        f"max |adapted - intrinsic| = {max_adapted_diff:.4f}h (bound {config.adapted_max_offset_hours}h)",
    )

    # 3. current_DLMO remains within configured bound
    current_diffs = [abs(circular_diff_hours(d.state.current_dlmo_hour, intrinsic)) for d in replay_days]
    max_current_diff = max(current_diffs)
    report.add(
        "current_within_bound",
        max_current_diff <= config.current_max_offset_hours + 1e-6,
        f"max |current - intrinsic| = {max_current_diff:.4f}h (bound {config.current_max_offset_hours}h)",
    )

    # 4. current DLMO changes continuously (no impossible jump)
    current_values = [d.state.current_dlmo_hour for d in replay_days]
    day_jumps = [
        abs(circular_diff_hours(current_values[i], current_values[i - 1])) for i in range(1, len(current_values))
    ]
    sanity_bound_hours = (
        (config.daily_continuity_cap_minutes / 60.0 + 1.5) if config.daily_continuity_cap_minutes else 4.0
    )
    max_jump = max(day_jumps) if day_jumps else 0.0
    report.add(
        "current_changes_continuously",
        max_jump < sanity_bound_hours,
        f"max single-day |change| = {max_jump:.3f}h (sanity bound {sanity_bound_hours:.2f}h)",
    )

    # 5. adapted DLMO changes more slowly than current DLMO, on average
    adapted_values = [d.state.adapted_dlmo_hour for d in replay_days]
    adapted_jumps = [
        abs(circular_diff_hours(adapted_values[i], adapted_values[i - 1])) for i in range(1, len(adapted_values))
    ]
    mean_adapted_jump = sum(adapted_jumps) / len(adapted_jumps) if adapted_jumps else 0.0
    mean_current_jump = sum(day_jumps) / len(day_jumps) if day_jumps else 0.0
    report.add(
        "adapted_moves_more_slowly_than_current",
        mean_adapted_jump <= mean_current_jump + 1e-9,
        f"mean adapted jump = {mean_adapted_jump:.4f}h, mean current jump = {mean_current_jump:.4f}h",
    )

    # 7. circular midnight behavior is correct (spot-check on a
    # constructed crossing, independent of the actual trajectory values)
    midnight_diff = circular_diff_hours(0.0 + 10 / 60, 23.0 + 50 / 60)
    report.add(
        "midnight_circular_arithmetic_correct",
        abs(abs(midnight_diff) - 20.0 / 60.0) < 1e-6,
        f"circular_diff(00:10, 23:50) = {midnight_diff * 60:.3f} minutes (expected +/-20)",
    )

    # 8. no NaN / infinity
    all_values = intrinsic_values | set(current_values) | set(adapted_values)
    bad_values = [v for v in all_values if math.isnan(v) or math.isinf(v)]
    report.add("no_nan_or_infinity", len(bad_values) == 0, f"bad values: {bad_values}" if bad_values else "all finite")

    # 9. no duplicate state transitions (each day produced exactly once,
    # and dates -- where provided -- are strictly increasing with no repeats)
    dates = [d.date for d in replay_days if d.date is not None]
    duplicate_dates = len(dates) != len(set(dates))
    strictly_increasing = all(dates[i] < dates[i + 1] for i in range(len(dates) - 1)) if dates else True
    report.add(
        "no_duplicate_state_transitions",
        not duplicate_dates and strictly_increasing,
        "no duplicates, strictly increasing" if (not duplicate_dates and strictly_increasing) else "duplicate or out-of-order dates found",
    )

    return report


def check_recovery_toward_equilibrium(
    traits: ParticipantPhaseTraits,
    disruptive_behavior: DailyBehaviorInputs,
    normal_behavior: DailyBehaviorInputs,
    disruption_days: int = 10,
    recovery_days: int = 20,
    config: StateEngineConfig = DEFAULT_STATE_ENGINE_CONFIG,
    source: SourceBackedAssumptions = DEFAULT_SOURCE_BACKED,
    synthetic: SyntheticAssumptions = DEFAULT_SYNTHETIC,
) -> ValidationReport:
    """Check 6: removing behavioral disturbance causes the state to tend
    back toward adapted/intrinsic equilibrium.

    Runs ``disruption_days`` of ``disruptive_behavior`` then
    ``recovery_days`` of ``normal_behavior``, and checks that the
    participant's distance from intrinsic DLMO is smaller at the end of
    the recovery period than at the peak of the disruption.
    """

    report = ValidationReport()
    state = initialize_state(traits.intrinsic_dlmo_hour, traits.chronotype, config)

    peak_distance = 0.0
    for _ in range(disruption_days):
        state, _ = step(state, disruptive_behavior, traits, config, source, synthetic)
        distance = abs(circular_diff_hours(state.current_dlmo_hour, state.intrinsic_dlmo_hour))
        peak_distance = max(peak_distance, distance)

    for _ in range(recovery_days):
        state, _ = step(state, normal_behavior, traits, config, source, synthetic)

    final_distance = abs(circular_diff_hours(state.current_dlmo_hour, state.intrinsic_dlmo_hour))

    report.add(
        "recovers_toward_equilibrium_after_disruption",
        final_distance < peak_distance,
        f"peak distance from intrinsic = {peak_distance:.3f}h, final distance after recovery = {final_distance:.3f}h",
    )
    return report


def check_determinism(
    state,
    behavior: DailyBehaviorInputs,
    traits: ParticipantPhaseTraits,
    config: StateEngineConfig = DEFAULT_STATE_ENGINE_CONFIG,
    source: SourceBackedAssumptions = DEFAULT_SOURCE_BACKED,
    synthetic: SyntheticAssumptions = DEFAULT_SYNTHETIC,
) -> ValidationReport:
    """Check 10: the same state + same inputs produce the same output,
    every time (the deterministic path takes no hidden randomness)."""

    report = ValidationReport()
    state_a, _ = step(state, behavior, traits, config, source, synthetic)
    state_b, _ = step(state, behavior, traits, config, source, synthetic)

    matches = (
        state_a.intrinsic_dlmo_hour == state_b.intrinsic_dlmo_hour
        and state_a.adapted_dlmo_hour == state_b.adapted_dlmo_hour
        and state_a.current_dlmo_hour == state_b.current_dlmo_hour
    )
    report.add(
        "deterministic_given_same_inputs",
        matches,
        "identical outputs" if matches else f"outputs differed: {state_a} vs {state_b}",
    )
    return report

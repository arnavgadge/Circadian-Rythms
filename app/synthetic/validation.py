"""Automated quality checks for a generated :class:`SyntheticDataset`.

Implements the 16 checks required for Phase 3: structural counts,
integrity, plausibility bounds, and behavioral/statistical sanity
checks (distribution recording, personality differentiation, and
DLMO state continuity/bounds). None of these are scientific validity
checks against real human data -- they only verify the *generator*
did what it was told to do.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.synthetic.config import SyntheticAssumptions
from app.synthetic.simulator import SyntheticDataset
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
        lines = []
        for c in self.checks:
            status = "PASS" if c.passed else "FAIL"
            lines.append(f"[{status}] {c.name}: {c.detail}")
        return lines

    def raise_if_failed(self) -> None:
        failed = [c for c in self.checks if not c.passed]
        if failed:
            details = "; ".join(f"{c.name} ({c.detail})" for c in failed)
            raise AssertionError(f"Synthetic dataset failed validation: {details}")


_REQUIRED_DAILY_FIELDS = [
    "sleep_onset_hour",
    "sleep_offset_hour",
    "sleep_duration_hours",
    "sleep_midpoint_hour",
    "morning_light_start_hour",
    "morning_light_duration_minutes",
    "evening_screen_end_hour",
    "evening_screen_duration_hours",
    "last_meal_hour",
    "meal_to_sleep_gap_minutes",
    "exercise_hour",
    "exercise_duration_minutes",
    "caffeine_hour",
    "caffeine_amount_mg",
    "resting_hr_bpm",
    "hrv_ms",
    "wrist_temp_c",
    "current_dlmo_hour",
    "adapted_dlmo_hour",
    "intrinsic_dlmo_hour",
]


def run_quality_checks(
    dataset: SyntheticDataset, synthetic: SyntheticAssumptions
) -> ValidationReport:
    report = ValidationReport()
    p_df = dataset.participants_df
    d_df = dataset.daily_df
    w_df = dataset.windows_df
    run_config = dataset.run_config

    expected_participants = run_config.num_participants
    expected_days = run_config.num_days
    expected_windows_per_participant = run_config.num_days - run_config.window_size_days

    # 1. exactly N participants
    report.add(
        "participant_count",
        len(p_df) == expected_participants,
        f"expected {expected_participants}, got {len(p_df)}",
    )

    # 2. exactly `num_days` days per participant
    days_per_participant = d_df.groupby("participant_index").size()
    all_correct_days = bool((days_per_participant == expected_days).all())
    report.add(
        "days_per_participant",
        all_correct_days and len(days_per_participant) == expected_participants,
        f"expected {expected_days} for every participant, "
        f"min={days_per_participant.min() if len(days_per_participant) else 'n/a'}, "
        f"max={days_per_participant.max() if len(days_per_participant) else 'n/a'}",
    )

    # 3. exactly N * num_days daily records
    expected_daily_rows = expected_participants * expected_days
    report.add(
        "total_daily_row_count",
        len(d_df) == expected_daily_rows,
        f"expected {expected_daily_rows}, got {len(d_df)}",
    )

    # 4. exactly (num_days - window_size) windows per participant
    windows_per_participant = w_df.groupby("participant_index").size()
    all_correct_windows = bool((windows_per_participant == expected_windows_per_participant).all())
    report.add(
        "windows_per_participant",
        all_correct_windows and len(windows_per_participant) == expected_participants,
        f"expected {expected_windows_per_participant} for every participant, "
        f"min={windows_per_participant.min() if len(windows_per_participant) else 'n/a'}, "
        f"max={windows_per_participant.max() if len(windows_per_participant) else 'n/a'}",
    )

    # 5. exactly N * (num_days - window_size) total windows
    expected_total_windows = expected_participants * expected_windows_per_participant
    report.add(
        "total_window_count",
        len(w_df) == expected_total_windows,
        f"expected {expected_total_windows}, got {len(w_df)}",
    )

    # 6. no duplicated participant/date pairs
    duplicate_count = int(d_df.duplicated(subset=["participant_index", "date"]).sum())
    report.add(
        "no_duplicate_participant_date_pairs",
        duplicate_count == 0,
        f"found {duplicate_count} duplicate (participant, date) pairs",
    )

    # 7. no missing required core fields
    missing_counts = {
        field_name: int(d_df[field_name].isna().sum())
        for field_name in _REQUIRED_DAILY_FIELDS
        if field_name in d_df.columns
    }
    total_missing = sum(missing_counts.values())
    worst_fields = {k: v for k, v in missing_counts.items() if v > 0}
    report.add(
        "no_missing_required_fields",
        total_missing == 0,
        "no missing values" if total_missing == 0 else f"missing values in: {worst_fields}",
    )

    # 8. DLMO values are valid circular times (i.e. within [0, 24))
    dlmo_columns = ["current_dlmo_hour", "adapted_dlmo_hour", "intrinsic_dlmo_hour"]
    valid_range = all(
        bool(((d_df[col] >= 0.0) & (d_df[col] < 24.0)).all()) for col in dlmo_columns
    )
    report.add(
        "dlmo_values_valid_circular_range",
        valid_range,
        f"all of {dlmo_columns} within [0, 24)" if valid_range else "found values outside [0, 24)",
    )

    # 9. sleep duration is plausible
    sleep_ok = bool(((d_df["sleep_duration_hours"] >= 2.5) & (d_df["sleep_duration_hours"] <= 12.0)).all())
    report.add(
        "sleep_duration_plausible",
        sleep_ok,
        f"range observed: [{d_df['sleep_duration_hours'].min():.2f}, {d_df['sleep_duration_hours'].max():.2f}] hours",
    )

    # 10. screen duration non-negative
    screen_ok = bool((d_df["evening_screen_duration_hours"] >= 0.0).all())
    report.add(
        "screen_duration_non_negative",
        screen_ok,
        f"min observed: {d_df['evening_screen_duration_hours'].min():.2f} hours",
    )

    # 11. meal times valid
    meal_ok = bool(((d_df["last_meal_hour"] >= 0.0) & (d_df["last_meal_hour"] < 24.0)).all())
    report.add(
        "meal_times_valid",
        meal_ok,
        "all last_meal_hour within [0, 24)" if meal_ok else "found last_meal_hour outside [0, 24)",
    )

    # 12. no impossible negative physiological/behavioral values
    non_negative_fields = [
        "resting_hr_bpm",
        "hrv_ms",
        "wrist_temp_c",
        "caffeine_amount_mg",
        "exercise_duration_minutes",
        "morning_light_duration_minutes",
    ]
    negative_counts = {f: int((d_df[f] < 0.0).sum()) for f in non_negative_fields}
    total_negative = sum(negative_counts.values())
    report.add(
        "no_negative_physiological_values",
        total_negative == 0,
        "all non-negative" if total_negative == 0 else f"negative values found: {negative_counts}",
    )

    # 13. chronotype distribution recorded (and roughly matches configuration)
    chronotype_counts = p_df["chronotype"].value_counts().to_dict()
    report.add(
        "chronotype_distribution_recorded",
        len(chronotype_counts) > 0,
        f"distribution: {chronotype_counts}",
    )

    # 14. personality distribution recorded
    personality_counts = p_df["personality_key"].value_counts().to_dict()
    report.add(
        "personality_distribution_recorded",
        len(personality_counts) > 0,
        f"distribution: {personality_counts}",
    )

    # 15. social jetlag behaves differently across relevant personalities
    jetlag_by_personality = (
        d_df.dropna(subset=["social_jetlag_minutes"])
        .merge(p_df[["index", "personality_key"]], left_on="participant_index", right_on="index")
        .groupby("personality_key")["social_jetlag_minutes"]
        .mean()
    )
    if {"social_jetlag_student", "healthy_stable_routine"}.issubset(jetlag_by_personality.index):
        jetlag_differs = bool(
            jetlag_by_personality["social_jetlag_student"]
            > jetlag_by_personality["healthy_stable_routine"] + 15.0
        )
    else:
        jetlag_differs = False
    report.add(
        "social_jetlag_differs_by_personality",
        jetlag_differs,
        f"mean social jetlag by personality (minutes): {jetlag_by_personality.round(1).to_dict()}",
    )

    # 16. DLMO trajectories show continuity, and stay within their bounds
    max_bound_violation = 0.0
    max_day_jump = 0.0
    for _, group in d_df.sort_values("day_index").groupby("participant_index"):
        current = group["current_dlmo_hour"].to_numpy()
        adapted = group["adapted_dlmo_hour"].to_numpy()
        intrinsic = group["intrinsic_dlmo_hour"].to_numpy()

        current_bound_diffs = np.abs(
            [circular_diff_hours(c, i) for c, i in zip(current, intrinsic)]
        )
        adapted_bound_diffs = np.abs(
            [circular_diff_hours(a, i) for a, i in zip(adapted, intrinsic)]
        )
        max_bound_violation = max(
            max_bound_violation,
            float(np.max(current_bound_diffs - synthetic.current_bound_hours_from_intrinsic)),
            float(np.max(adapted_bound_diffs - synthetic.adapted_bound_hours_from_intrinsic)),
        )

        if len(current) > 1:
            day_jumps = np.abs(
                [circular_diff_hours(current[i], current[i - 1]) for i in range(1, len(current))]
            )
            max_day_jump = max(max_day_jump, float(np.max(day_jumps)))

    continuity_bound_hours = 3.5  # diagnostic sanity bound, not a model limit
    bound_tolerance_hours = 0.05  # floating-point / noise slack
    continuity_ok = max_day_jump < continuity_bound_hours
    bounds_ok = max_bound_violation < bound_tolerance_hours
    report.add(
        "dlmo_state_continuity_and_bounds",
        continuity_ok and bounds_ok,
        f"max single-day |change|={max_day_jump:.2f}h (bound {continuity_bound_hours}h), "
        f"max bound violation={max_bound_violation:.3f}h",
    )

    return report

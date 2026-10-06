"""Automated feature sanity checks.

Implements the 15 checks required for Phase 4: manifest integrity,
value-range sanity, temporal ordering/leakage, and the explicit
"forbidden feature" checks (no direct sleep-onset/offset/midpoint
feature, no physiology feature) that enforce the anti-circularity rule
and the Version-1 architecture lock structurally, not just by review.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta

from app.features.builder import FeatureVector
from app.features.feature_manifest import FEATURE_NAMES, MANIFEST, TOTAL_FEATURE_COUNT


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
            raise AssertionError(
                "Feature vector failed validation: " + "; ".join(f"{c.name} ({c.detail})" for c in failed)
            )


_FORBIDDEN_NAME_SUBSTRINGS = (
    "sleep_onset",
    "sleep_offset",
    "sleep_midpoint_sin",
    "sleep_midpoint_cos",
    "weighted_sleep_onset",
    "resting_hr",
    "hrv",
    "wrist_temp",
)

_RATIO_FEATURES = ("exercise_frequency_ratio", "free_day_ratio")
_DURATION_FEATURES = (
    "sleep_duration_mean_hours",
    "sleep_duration_std_hours",
    "sleep_duration_recency_weighted_hours",
    "screen_duration_mean_hours",
    "screen_duration_recency_weighted_hours",
    "morning_light_duration_mean_minutes",
    "morning_light_duration_recency_weighted_minutes",
    "exercise_duration_mean_minutes",
    "caffeine_amount_mean_mg",
    "caffeine_amount_recency_weighted_mg",
)


def validate_feature_vector(fv: FeatureVector) -> ValidationReport:
    report = ValidationReport()

    # 1. expected feature count = 68
    report.add(
        "feature_count",
        len(fv.feature_names) == TOTAL_FEATURE_COUNT and len(fv.features) == TOTAL_FEATURE_COUNT,
        f"expected {TOTAL_FEATURE_COUNT}, got {len(fv.features)}",
    )

    # 2. no duplicate feature names
    report.add(
        "no_duplicate_feature_names",
        len(fv.feature_names) == len(set(fv.feature_names)),
        f"{len(fv.feature_names)} names, {len(set(fv.feature_names))} unique",
    )

    # 3. no NaN after allowed imputation
    nan_features = [name for name, value in fv.features.items() if value is None or _is_nan(value)]
    report.add("no_nan_values", len(nan_features) == 0, f"NaN/None features: {nan_features}")

    # 4. no infinite values
    inf_features = [name for name, value in fv.features.items() if _is_inf(value)]
    report.add("no_infinite_values", len(inf_features) == 0, f"infinite features: {inf_features}")

    # 5. all circular values bounded to [-1, 1]
    circular_specs = [s for s in MANIFEST if s.circular]
    out_of_bounds = [
        s.name for s in circular_specs if not (-1.0 - 1e-9 <= fv.features[s.name] <= 1.0 + 1e-9)
    ]
    report.add(
        "circular_values_bounded",
        len(out_of_bounds) == 0,
        "all sin/cos in [-1, 1]" if not out_of_bounds else f"out of bounds: {out_of_bounds}",
    )

    # 6. durations are non-negative
    negative_durations = [name for name in _DURATION_FEATURES if fv.features.get(name, 0) < 0]
    report.add(
        "durations_non_negative",
        len(negative_durations) == 0,
        "all durations >= 0" if not negative_durations else f"negative durations: {negative_durations}",
    )

    # 7. ratios within [0, 1]
    out_of_range_ratios = [
        name for name in _RATIO_FEATURES if not (0.0 - 1e-9 <= fv.features.get(name, 0) <= 1.0 + 1e-9)
    ]
    report.add(
        "ratios_within_expected_range",
        len(out_of_range_ratios) == 0,
        "all ratios in [0, 1]" if not out_of_range_ratios else f"out of range: {out_of_range_ratios}",
    )

    # 8. MEQ normalized is [0, 1]
    meq_norm = fv.features.get("meq_normalized")
    report.add(
        "meq_normalized_in_range",
        meq_norm is not None and 0.0 - 1e-9 <= meq_norm <= 1.0 + 1e-9,
        f"meq_normalized={meq_norm}",
    )

    # 9. temporal ordering is correct (window strictly increasing, 6 consecutive days)
    ordering_ok = (fv.window_end - fv.window_start) == timedelta(days=5)
    report.add(
        "temporal_ordering_correct",
        ordering_ok,
        f"window_start={fv.window_start}, window_end={fv.window_end}",
    )

    # 10. target-day data is not included (window ends exactly 1 day before target)
    leakage_ok = (fv.target_date - fv.window_end) == timedelta(days=1)
    report.add(
        "target_day_excluded",
        leakage_ok,
        f"target_date={fv.target_date}, window_end={fv.window_end}",
    )

    # 11-13. no direct sleep-onset/offset/midpoint feature
    # 15. physiology features absent from V1
    forbidden_hits = [
        name for name in fv.feature_names for pattern in _FORBIDDEN_NAME_SUBSTRINGS if pattern in name
    ]
    report.add(
        "no_direct_sleep_onset_feature",
        not any("sleep_onset" in n for n in fv.feature_names),
        "confirmed absent" if not any("sleep_onset" in n for n in fv.feature_names) else str(forbidden_hits),
    )
    report.add(
        "no_direct_sleep_offset_feature",
        not any("sleep_offset" in n for n in fv.feature_names),
        "confirmed absent" if not any("sleep_offset" in n for n in fv.feature_names) else str(forbidden_hits),
    )
    report.add(
        "no_direct_sleep_midpoint_sincos_feature",
        not any(("sleep_midpoint_sin" in n or "sleep_midpoint_cos" in n) for n in fv.feature_names),
        "confirmed absent",
    )

    # 14. no weighted sleep-onset feature
    report.add(
        "no_weighted_sleep_onset_feature",
        not any("weighted_sleep_onset" in n for n in fv.feature_names),
        "confirmed absent",
    )

    # 15. physiology absent
    physiology_patterns = ("resting_hr", "hrv", "wrist_temp")
    report.add(
        "physiology_absent_from_v1",
        not any(any(p in n for p in physiology_patterns) for n in fv.feature_names),
        "confirmed absent",
    )

    return report


def _is_nan(value) -> bool:
    try:
        return math.isnan(value)
    except TypeError:
        return False


def _is_inf(value) -> bool:
    try:
        return math.isinf(value)
    except TypeError:
        return False

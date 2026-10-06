"""Tests for circular evaluation utilities and metrics."""

from __future__ import annotations

import numpy as np
import pytest

from app.models.config import SuccessTargets
from app.models.evaluation import (
    check_success_targets,
    circular_error_minutes,
    circular_errors_minutes,
    compute_metrics,
    stratified_metrics,
)


def test_circular_error_midnight_crossing_is_20_minutes_not_23h40():
    # Sign convention is actual - predicted (shortest arc); the brief
    # accepts either sign here, so this checks magnitude.
    error = circular_error_minutes(23.0 + 50 / 60, 0.0 + 10 / 60)
    assert abs(error) == pytest.approx(20.0, abs=0.01)
    assert abs(error) < 30  # nowhere near 23h40m = 1420 minutes


def test_circular_error_sign_convention():
    # actual later than predicted -> positive
    assert circular_error_minutes(10.0, 9.0) > 0
    # actual earlier than predicted -> negative
    assert circular_error_minutes(9.0, 10.0) < 0


def test_circular_error_zero_for_identical_times():
    assert circular_error_minutes(14.25, 14.25) == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("hour", [0.0, 6.0, 12.0, 18.0, 23.0 + 59 / 60])
def test_circular_error_known_clock_points_against_self(hour):
    assert circular_error_minutes(hour, hour) == pytest.approx(0.0, abs=1e-9)


def test_circular_errors_minutes_vectorized_matches_scalar():
    actual = np.array([23.0 + 50 / 60, 12.0, 0.5])
    predicted = np.array([0.0 + 10 / 60, 12.5, 23.5])
    vectorized = circular_errors_minutes(actual, predicted)
    scalar = [circular_error_minutes(a, p) for a, p in zip(actual, predicted)]
    np.testing.assert_allclose(vectorized, scalar, atol=1e-9)


def test_compute_metrics_perfect_predictions():
    hours = np.array([1.0, 12.0, 23.0])
    metrics = compute_metrics(hours, hours)
    assert metrics.mae_minutes == pytest.approx(0.0, abs=1e-9)
    assert metrics.rmse_minutes == pytest.approx(0.0, abs=1e-9)
    assert metrics.pct_within_15_min == pytest.approx(100.0)


def test_compute_metrics_known_offset():
    actual = np.array([12.0, 12.0, 12.0, 12.0])
    predicted = np.array([12.5, 12.5, 12.5, 12.5])  # 30 min off every time
    metrics = compute_metrics(actual, predicted)
    assert metrics.mae_minutes == pytest.approx(30.0, abs=0.01)
    assert metrics.pct_within_30_min == pytest.approx(100.0)
    assert metrics.pct_within_15_min == pytest.approx(0.0)


def test_compute_metrics_requires_nonempty_input():
    with pytest.raises(ValueError):
        compute_metrics(np.array([]), np.array([]))


def test_compute_metrics_percentiles_ordered():
    rng = np.random.default_rng(0)
    actual = rng.uniform(0, 24, 200)
    predicted = rng.uniform(0, 24, 200)
    metrics = compute_metrics(actual, predicted)
    assert metrics.p90_absolute_error_minutes <= metrics.p95_absolute_error_minutes


def test_stratified_metrics_groups_correctly():
    actual = np.array([12.0, 12.0, 6.0, 6.0])
    predicted = np.array([12.0, 12.5, 6.0, 7.0])
    groups = np.array(["A", "A", "B", "B"])
    result = stratified_metrics(actual, predicted, groups)
    assert set(result["group"]) == {"A", "B"}
    row_a = result[result["group"] == "A"].iloc[0]
    assert row_a["n_windows"] == 2
    assert row_a["mae_minutes"] == pytest.approx(15.0, abs=0.01)


def test_stratified_metrics_includes_participant_count_when_given():
    actual = np.array([1.0, 2.0, 3.0])
    predicted = np.array([1.0, 2.0, 3.0])
    groups = np.array(["A", "A", "B"])
    participant_ids = np.array([100, 100, 200])
    result = stratified_metrics(actual, predicted, groups, participant_ids)
    assert "n_participants" in result.columns
    assert result[result["group"] == "A"]["n_participants"].iloc[0] == 1


def test_check_success_targets_classification():
    targets = SuccessTargets()
    assert check_success_targets(30.0, 90.0, targets) == "excellent"
    assert check_success_targets(40.0, 82.0, targets) == "good"
    assert check_success_targets(55.0, 72.0, targets) == "minimum"
    assert check_success_targets(90.0, 40.0, targets) == "below_minimum"

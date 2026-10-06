"""Tests for the reusable circular clock-time utilities."""

from __future__ import annotations

from datetime import time

import pytest

from app.synthetic.time_utils import (
    circular_diff_hours,
    circular_diff_minutes,
    circular_mean_hours,
    circular_std_hours,
    clock_time_to_hour,
    hour_to_clock_time,
    normalize_hour,
)


def test_normalize_hour_wraps_into_0_24():
    assert normalize_hour(25.0) == pytest.approx(1.0)
    assert normalize_hour(-1.0) == pytest.approx(23.0)
    assert normalize_hour(12.0) == pytest.approx(12.0)


def test_hour_to_clock_time_and_back_round_trip():
    t = hour_to_clock_time(23.5)
    assert t == time(23, 30, 0)
    assert clock_time_to_hour(t) == pytest.approx(23.5)


def test_circular_diff_treats_midnight_as_close():
    # 23:50 vs 00:10 are only 20 minutes apart, not ~23h40m.
    diff = circular_diff_minutes(0.0 + 10 / 60, 23.0 + 50 / 60)
    assert diff == pytest.approx(20.0, abs=0.01)


def test_circular_diff_is_signed_and_antisymmetric():
    a, b = 1.0, 23.0
    assert circular_diff_hours(a, b) == pytest.approx(-circular_diff_hours(b, a))


def test_circular_diff_naive_linear_subtraction_would_be_wrong():
    # A plain (a - b) would give -23.67, which is not the shortest arc.
    naive = (0.17 - 23.83)
    correct = circular_diff_hours(0.17, 23.83)
    assert abs(naive) > 20  # the naive value is nonsensically large
    assert abs(correct) < 1  # the correct circular distance is small


def test_circular_mean_of_values_straddling_midnight():
    # 23:00 and 01:00 should average to 00:00, not 12:00.
    mean = circular_mean_hours([23.0, 1.0])
    assert mean == pytest.approx(0.0, abs=1e-6) or mean == pytest.approx(24.0, abs=1e-6)


def test_circular_mean_requires_at_least_one_value():
    with pytest.raises(ValueError):
        circular_mean_hours([])


def test_circular_std_of_identical_values_is_zero():
    assert circular_std_hours([10.0, 10.0, 10.0]) == pytest.approx(0.0, abs=1e-9)


def test_circular_std_of_dispersed_values_is_positive():
    assert circular_std_hours([0.0, 6.0, 12.0, 18.0]) > 0.0

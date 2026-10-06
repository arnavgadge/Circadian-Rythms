"""Tests for the ML-facing circular time encoding (sin/cos)."""

from __future__ import annotations

import math
from datetime import time

import pytest

from app.features.time_encoding import (
    clock_to_sincos,
    sincos_to_clock,
    sincos_to_time,
    time_to_sincos,
)


def test_clock_to_sincos_bounded_in_unit_range():
    for hour in [0.0, 6.0, 12.0, 18.0, 23.99]:
        sin_val, cos_val = clock_to_sincos(hour)
        assert -1.0 <= sin_val <= 1.0
        assert -1.0 <= cos_val <= 1.0


def test_clock_to_sincos_known_points():
    # Midnight: angle 0 -> sin=0, cos=1
    sin_val, cos_val = clock_to_sincos(0.0)
    assert sin_val == pytest.approx(0.0, abs=1e-9)
    assert cos_val == pytest.approx(1.0, abs=1e-9)

    # Noon: angle pi -> sin=0, cos=-1
    sin_val, cos_val = clock_to_sincos(12.0)
    assert sin_val == pytest.approx(0.0, abs=1e-9)
    assert cos_val == pytest.approx(-1.0, abs=1e-9)

    # 18:00: angle 3pi/2 -> sin=-1, cos=0
    sin_val, cos_val = clock_to_sincos(18.0)
    assert sin_val == pytest.approx(-1.0, abs=1e-9)
    assert cos_val == pytest.approx(0.0, abs=1e-9)


def test_round_trip_clock_to_sincos_and_back():
    for hour in [0.0, 1.5, 6.25, 12.0, 18.75, 23.99]:
        sin_val, cos_val = clock_to_sincos(hour)
        recovered = sincos_to_clock(sin_val, cos_val)
        assert recovered == pytest.approx(hour, abs=1e-6)


def test_23_59_and_00_00_are_numerically_close_in_sincos_space():
    """The whole point of circular encoding: 23:59 and 00:00 must be
    close in (sin, cos) space even though they are numerically far apart
    as plain scalars (23.98 vs 0.0)."""

    a = clock_to_sincos(23.0 + 59 / 60)
    b = clock_to_sincos(0.0)
    distance = math.hypot(a[0] - b[0], a[1] - b[1])
    assert distance < 0.02  # ~1 minute apart on a 24h circle


def test_midnight_crossing_23_50_vs_00_10_is_close_in_sincos_space():
    a = clock_to_sincos(23.0 + 50 / 60)
    b = clock_to_sincos(0.0 + 10 / 60)
    distance = math.hypot(a[0] - b[0], a[1] - b[1])
    # 20 minutes apart on a 24h circle is a small angular distance.
    assert distance < 0.09


def test_far_apart_times_are_numerically_far_in_sincos_space():
    a = clock_to_sincos(6.0)
    b = clock_to_sincos(18.0)
    distance = math.hypot(a[0] - b[0], a[1] - b[1])
    assert distance > 1.5  # opposite sides of the circle


def test_time_to_sincos_and_back_round_trip():
    t = time(23, 50, 0)
    encoded = time_to_sincos(t)
    decoded = sincos_to_time(*encoded)
    # Allow a small tolerance from the seconds-rounding in hour_to_clock_time.
    assert abs(decoded.hour * 60 + decoded.minute - (t.hour * 60 + t.minute)) <= 1


def test_time_to_sincos_of_none_is_none():
    assert time_to_sincos(None) is None

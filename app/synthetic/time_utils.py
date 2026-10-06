"""Reusable circular clock-time utilities.

Clock times wrap at midnight: 23:50 and 00:10 are 20 minutes apart, not
23 hours and 40 minutes apart. Every function here treats a clock time
as a point on a 24-hour circle rather than a plain float, so 00:00 is
never accidentally treated as "smaller than" 23:59.

Two representations are used throughout ``app.synthetic``:

- **clock hour**: a float in ``[0, 24)``, e.g. ``23.5`` for 23:30.
- ``datetime.time``: for storage in the Phase 2 schema's ``Time``
  columns.

These utilities are intentionally free of any ML-specific circular
encoding (sin/cos) -- that belongs to the Phase 4 feature-engineering
layer, not here.
"""

from __future__ import annotations

import math
from datetime import time
from typing import Iterable

HOURS_PER_DAY = 24.0


def normalize_hour(hour: float) -> float:
    """Wrap an arbitrary hour value into ``[0, 24)``.

    Python's ``%`` mathematically guarantees a result in ``[0, 24)`` for
    a finite divisor, but a tiny negative floating-point input (e.g.
    ``-7.1e-16``, which arises routinely from chained circular-arithmetic
    subtraction/addition elsewhere in this module) can round to exactly
    ``24.0`` in float64 -- silently violating the documented half-open
    contract every caller relies on (a downstream ``hour_to_clock_time``
    would then wrap that back to ``00:00:00`` via its own modulo, but
    any caller comparing against ``< 24.0`` directly would not). Guard
    against that rounding edge case explicitly rather than relying on
    every caller to re-guard it.
    """

    result = hour % HOURS_PER_DAY
    if result >= HOURS_PER_DAY:
        result -= HOURS_PER_DAY
    return result


def hour_to_clock_time(hour: float) -> time:
    """Convert a continuous hour value (may be outside ``[0, 24)``) to a
    :class:`datetime.time`, rounded to the nearest second."""

    normalized = normalize_hour(hour)
    total_seconds = round(normalized * 3600)
    total_seconds %= 24 * 3600
    hh, remainder = divmod(total_seconds, 3600)
    mm, ss = divmod(remainder, 60)
    return time(hour=hh, minute=mm, second=ss)


def clock_time_to_hour(value: time) -> float:
    """Convert a :class:`datetime.time` to a continuous hour value in
    ``[0, 24)``."""

    return value.hour + value.minute / 60.0 + value.second / 3600.0


def hours_to_minutes(hours: float) -> float:
    return hours * 60.0


def minutes_to_hours(minutes: float) -> float:
    return minutes / 60.0


def add_hours(hour: float, delta_hours: float) -> float:
    """Add a (possibly negative) offset to a clock hour, wrapping at 24h."""

    return normalize_hour(hour + delta_hours)


def circular_diff_hours(a_hour: float, b_hour: float) -> float:
    """Signed shortest circular difference ``a - b`` in hours, in ``(-12, 12]``.

    Positive means ``a`` is later than ``b`` along the shorter arc; e.g.
    ``circular_diff_hours(0.17, 23.83)`` (00:10 vs 23:50) is ``+0.33``
    (20 minutes), not ``-23.67``.
    """

    diff = (a_hour - b_hour + 12.0) % HOURS_PER_DAY - 12.0
    # Python's % can return -12.0 for an exact half-day difference; normalize
    # that edge case to +12.0 so the range is consistently (-12, 12].
    if diff <= -12.0:
        diff += HOURS_PER_DAY
    return diff


def circular_diff_minutes(a_hour: float, b_hour: float) -> float:
    """Same as :func:`circular_diff_hours`, expressed in minutes."""

    return hours_to_minutes(circular_diff_hours(a_hour, b_hour))


def circular_mean_hours(hours: Iterable[float]) -> float:
    """Circular mean of a set of clock hours, returned in ``[0, 24)``.

    Computed via the mean resultant vector on the unit circle, which is
    the standard way to average circular quantities (a plain arithmetic
    mean of, say, 23:00 and 01:00 would wrongly produce 12:00 instead of
    00:00).
    """

    hours = list(hours)
    if not hours:
        raise ValueError("circular_mean_hours requires at least one value")

    angles = [h / HOURS_PER_DAY * 2 * math.pi for h in hours]
    sin_sum = sum(math.sin(a) for a in angles)
    cos_sum = sum(math.cos(a) for a in angles)

    if abs(sin_sum) < 1e-12 and abs(cos_sum) < 1e-12:
        # Perfectly opposed values (e.g. 06:00 and 18:00) have an
        # undefined circular mean direction; fall back to 0.0 rather
        # than raising, since callers deal with noisy synthetic data.
        return 0.0

    mean_angle = math.atan2(sin_sum, cos_sum)
    mean_hour = mean_angle / (2 * math.pi) * HOURS_PER_DAY
    return normalize_hour(mean_hour)


def circular_std_hours(hours: Iterable[float]) -> float:
    """Circular standard deviation of a set of clock hours, in hours.

    Uses the standard circular-statistics definition based on the mean
    resultant length ``R``: ``sqrt(-2 * ln(R))`` radians, converted to
    hours. Returns ``0.0`` for zero or one input values.
    """

    hours = list(hours)
    if len(hours) < 2:
        return 0.0

    angles = [h / HOURS_PER_DAY * 2 * math.pi for h in hours]
    sin_mean = sum(math.sin(a) for a in angles) / len(angles)
    cos_mean = sum(math.cos(a) for a in angles) / len(angles)
    resultant_length = min(1.0, math.hypot(sin_mean, cos_mean))

    if resultant_length <= 1e-12:
        return HOURS_PER_DAY / 4.0  # maximally dispersed

    angular_std = math.sqrt(-2.0 * math.log(resultant_length))
    return angular_std / (2 * math.pi) * HOURS_PER_DAY

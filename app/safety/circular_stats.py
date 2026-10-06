"""Circular-time statistics for the safety layer's rolling pattern
detectors. Reuses ``app.synthetic.time_utils`` for mean/diff (never
recomputed); adds a transparent trend estimator and a wraparound-safe
"how late/early" comparison, both documented in full since Phase 14's
brief explicitly requires the trend method to be documented.
"""

from __future__ import annotations

from datetime import date as date_cls
from typing import Optional, Sequence

from app.synthetic.time_utils import circular_diff_hours, circular_mean_hours


def unwrap_circular_series(hours: Sequence) -> list:
    """Turns a sequence of clock hours into a continuous (non-wrapping)
    trajectory by accumulating the shortest circular step between each
    consecutive pair -- 23:50 -> 00:05 -> 00:20 becomes
    ``[23.83, 24.08, 24.33]``, a smoothly increasing sequence, rather
    than a discontinuous jump back to ``0.08``. This is the same
    standard "unwrap" technique used for any circular/angular
    trajectory (and the same idea Phase 12's matched-period slope
    already applies to a DLMO series, applied here independently for
    the rolling drift detector's own purpose)."""

    hours = list(hours)
    if not hours:
        return []
    unwrapped = [hours[0]]
    for h in hours[1:]:
        unwrapped.append(unwrapped[-1] + circular_diff_hours(h, unwrapped[-1] % 24.0))
    return unwrapped


def _ols_slope(x: Sequence, y: Sequence) -> Optional[float]:
    n = len(x)
    if n < 2:
        return None
    x_mean, y_mean = sum(x) / n, sum(y) / n
    covariance = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    variance = sum((xi - x_mean) ** 2 for xi in x)
    if variance <= 1e-9:
        return None
    return covariance / variance


def compute_circular_trend_minutes_per_day(dated_hours: Sequence) -> Optional[float]:
    """``dated_hours``: ``[(date, hour), ...]``, any order, unique dates.
    Unwraps the circular series (see above) and fits an ordinary
    least-squares slope against **calendar-day offset from the first
    observation** (not observation index) -- so a gap in the data
    (missing/unavailable days) does not compress the fitted trend into
    too few elapsed days. Returns minutes/day (positive = getting
    later, negative = getting earlier), or ``None`` with fewer than 2
    points or zero elapsed-day spread."""

    pairs = sorted(dated_hours, key=lambda p: p[0])
    if len(pairs) < 2:
        return None

    dates = [p[0] for p in pairs]
    hours = [p[1] for p in pairs]
    unwrapped = unwrap_circular_series(hours)
    day_offsets = [(d - dates[0]).days for d in dates]

    slope_hours_per_day = _ols_slope(day_offsets, unwrapped)
    return slope_hours_per_day * 60.0 if slope_hours_per_day is not None else None


def circular_mean_of_available(hours: Sequence) -> Optional[float]:
    present = [h for h in hours if h is not None]
    return circular_mean_hours(present) if present else None


def signed_offset_from_midnight(hour: float) -> float:
    """Maps a clock hour to a signed offset from midnight in
    ``(-12, 12]`` -- ``18:00 -> -6.0``, ``23:00 -> -1.0``, ``00:00 -> 0.0``,
    ``02:00 -> +2.0``, ``06:00 -> +6.0``. Monotonically increasing across
    the entire evening/night/early-morning arc real DLMO values occupy,
    with its one discontinuity placed at **noon** -- far outside any
    plausible DLMO value -- so "later than 2:00 AM" / "earlier than
    7:30 PM" can be compared as ordinary signed numbers without the
    wraparound ambiguity a raw ``hour < threshold`` comparison would
    have for a post-midnight value. Valid specifically because DLMO
    never falls near noon in practice (the same kind of domain-specific
    simplification Phase 8's meal-timing component already documents
    for its own raw-float comparison)."""

    return hour - 24.0 if hour >= 12.0 else hour

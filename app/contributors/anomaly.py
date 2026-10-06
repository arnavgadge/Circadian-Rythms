"""Today's anomaly detection -- a concept deliberately separate from the
six-day habit-level contributor ranking (see module docstring in
``app.contributors.engine``).

Uses a **robust, median/MAD-based** statistic rather than a mean/
standard-deviation z-score, since six observations is too few for an
ordinary standard deviation to be a stable measure of spread (a single
outlier day can inflate or deflate it substantially), and a personal
window can easily have zero or near-zero variance (e.g. a very
consistent sleeper), which would make an ordinary z-score explode or
divide by zero.

The "modified z-score" (`0.6745 * (x - median) / MAD`) is a standard
robust-statistics technique (Iglewicz & Hoaglin); the threshold used to
call something an outlier (3.5) is their commonly-cited default, used
here as a reasonable, documented, configurable starting point -- **not**
claimed to be validated specifically for circadian behavioral data.

When the personal window's MAD is (numerically) zero -- every day
identical -- the modified z-score is undefined; the method falls back
to a fixed absolute-deviation threshold instead, so a genuinely novel
value against a perfectly stable history is still caught.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Optional, Sequence

from app.contributors.config import DEFAULT_CONTRIBUTOR_CONFIG, ContributorConfig
from app.synthetic.time_utils import circular_diff_hours, circular_mean_hours


def _is_missing(value) -> bool:
    """True for ``None`` or NaN -- see the identical helper in
    ``app.contributors.phase_effects`` for why both must be treated as
    missing (window values may be sourced from a database or a pandas
    DataFrame, which represent "missing" differently)."""

    return value is None or (isinstance(value, float) and math.isnan(value))


@dataclass(frozen=True)
class AnomalyResult:
    signal: str
    is_anomaly: bool
    available: bool
    today_value: Optional[float]
    baseline_center: Optional[float]
    deviation: Optional[float]  # today - baseline_center, in the signal's native units (minutes for circular)
    modified_z_score: Optional[float]
    method: str  # "modified_z" | "fallback_absolute" | "unavailable"


def _unavailable(signal: str) -> AnomalyResult:
    return AnomalyResult(signal, False, False, None, None, None, None, "unavailable")


def detect_anomaly_numeric(
    signal: str,
    today_value: Optional[float],
    window_values: Sequence,
    config: ContributorConfig = DEFAULT_CONTRIBUTOR_CONFIG,
) -> AnomalyResult:
    """For plain numeric quantities (durations, amounts) -- ordinary
    (non-circular) deviation."""

    baseline = [v for v in window_values if not _is_missing(v)]
    if _is_missing(today_value) or len(baseline) < config.min_history_days_for_anomaly:
        return _unavailable(signal)

    median = statistics.median(baseline)
    mad = statistics.median([abs(v - median) for v in baseline])
    deviation = today_value - median

    if mad < config.mad_epsilon:
        is_anomaly = abs(deviation) > config.fallback_absolute_threshold_minutes
        return AnomalyResult(signal, is_anomaly, True, today_value, median, deviation, None, "fallback_absolute")

    modified_z = 0.6745 * deviation / mad
    is_anomaly = abs(modified_z) > config.anomaly_modified_z_threshold
    return AnomalyResult(signal, is_anomaly, True, today_value, median, deviation, modified_z, "modified_z")


def detect_anomaly_circular(
    signal: str,
    today_hour: Optional[float],
    window_hours: Sequence,
    config: ContributorConfig = DEFAULT_CONTRIBUTOR_CONFIG,
) -> AnomalyResult:
    """For clock-time quantities -- circular center and circular deviations,
    so a value just after midnight is never mistaken for a huge outlier
    relative to a baseline clustered just before midnight."""

    baseline = [v for v in window_hours if not _is_missing(v)]
    if _is_missing(today_hour) or len(baseline) < config.min_history_days_for_anomaly:
        return _unavailable(signal)

    center = circular_mean_hours(baseline)
    circular_deviations_minutes = [circular_diff_hours(v, center) * 60.0 for v in baseline]
    median_deviation = statistics.median(circular_deviations_minutes)
    mad = statistics.median([abs(d - median_deviation) for d in circular_deviations_minutes])

    today_deviation_minutes = circular_diff_hours(today_hour, center) * 60.0
    centered_deviation = today_deviation_minutes - median_deviation

    if mad < config.mad_epsilon:
        is_anomaly = abs(centered_deviation) > config.fallback_absolute_threshold_minutes
        return AnomalyResult(
            signal, is_anomaly, True, today_hour, center, today_deviation_minutes, None, "fallback_absolute"
        )

    modified_z = 0.6745 * centered_deviation / mad
    is_anomaly = abs(modified_z) > config.anomaly_modified_z_threshold
    return AnomalyResult(
        signal, is_anomaly, True, today_hour, center, today_deviation_minutes, modified_z, "modified_z"
    )

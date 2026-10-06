"""Circular-time evaluation utilities.

Every error reported anywhere in Phase 5 is a **circular** difference:
23:50 vs. 00:10 is a 20-minute error, never ~23h40m. All metrics here
are computed on decoded clock hours (post
:func:`app.models.target_encoding.decode_predictions`), never on raw
sin/cos component error, since component-wise MSE does not correspond
to a clock-time error a human (or a downstream alignment engine) would
recognize.

Sign convention: ``circular_error_minutes(actual, predicted) = actual
- predicted``, shortest signed arc, in ``(-720, 720]`` minutes. Positive
means the actual DLMO is later than the prediction (the model
predicted too early); negative means the model predicted too late.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from app.synthetic.time_utils import circular_diff_hours


def circular_error_minutes(actual_hour: float, predicted_hour: float) -> float:
    """Signed shortest circular error, in minutes: ``actual - predicted``."""

    return circular_diff_hours(actual_hour, predicted_hour) * 60.0


def circular_errors_minutes(actual_hours: np.ndarray, predicted_hours: np.ndarray) -> np.ndarray:
    """Vectorized :func:`circular_error_minutes` over two hour arrays."""

    actual_hours = np.asarray(actual_hours, dtype=float)
    predicted_hours = np.asarray(predicted_hours, dtype=float)
    diff = (actual_hours - predicted_hours + 12.0) % 24.0 - 12.0
    diff = np.where(diff <= -12.0, diff + 24.0, diff)
    return diff * 60.0


@dataclass
class MetricsResult:
    """All primary metrics, computed from signed circular errors (minutes)."""

    n: int
    mae_minutes: float
    rmse_minutes: float
    median_absolute_error_minutes: float
    pct_within_15_min: float
    pct_within_30_min: float
    pct_within_60_min: float
    pct_within_90_min: float
    signed_mean_error_minutes: float
    signed_std_error_minutes: float
    p90_absolute_error_minutes: float
    p95_absolute_error_minutes: float

    def to_dict(self) -> dict:
        return asdict(self)


def compute_metrics(actual_hours: np.ndarray, predicted_hours: np.ndarray) -> MetricsResult:
    """Compute the 11 primary circular-time metrics.

    All percentages are 0-100. ``n`` is the number of rows the metrics
    were computed over; callers must not silently drop rows before
    calling this (see ``app.models.sanity``) -- if rows were legitimately
    excluded, that should be visible in ``n`` relative to the input size.
    """

    actual_hours = np.asarray(actual_hours, dtype=float)
    predicted_hours = np.asarray(predicted_hours, dtype=float)
    n = len(actual_hours)
    if n == 0:
        raise ValueError("compute_metrics requires at least one row")

    errors = circular_errors_minutes(actual_hours, predicted_hours)
    abs_errors = np.abs(errors)

    return MetricsResult(
        n=n,
        mae_minutes=float(np.mean(abs_errors)),
        rmse_minutes=float(np.sqrt(np.mean(errors**2))),
        median_absolute_error_minutes=float(np.median(abs_errors)),
        pct_within_15_min=float(np.mean(abs_errors <= 15.0) * 100.0),
        pct_within_30_min=float(np.mean(abs_errors <= 30.0) * 100.0),
        pct_within_60_min=float(np.mean(abs_errors <= 60.0) * 100.0),
        pct_within_90_min=float(np.mean(abs_errors <= 90.0) * 100.0),
        signed_mean_error_minutes=float(np.mean(errors)),
        signed_std_error_minutes=float(np.std(errors)),
        p90_absolute_error_minutes=float(np.percentile(abs_errors, 90)),
        p95_absolute_error_minutes=float(np.percentile(abs_errors, 95)),
    )


def stratified_metrics(
    actual_hours: np.ndarray,
    predicted_hours: np.ndarray,
    group_labels: np.ndarray,
    participant_ids: np.ndarray | None = None,
) -> pd.DataFrame:
    """Compute metrics separately for each distinct value in ``group_labels``.

    Returns one row per group with ``n_windows`` (and, if
    ``participant_ids`` is given, ``n_participants``) plus the subset of
    metrics the brief asks to report per stratum: MAE, median absolute
    error, RMSE, % within 30/60 min, and bias.
    """

    df = pd.DataFrame(
        {
            "actual_hour": np.asarray(actual_hours, dtype=float),
            "predicted_hour": np.asarray(predicted_hours, dtype=float),
            "group": group_labels,
        }
    )
    if participant_ids is not None:
        df["participant_id"] = participant_ids

    rows = []
    for group_value, sub in df.groupby("group"):
        metrics = compute_metrics(sub["actual_hour"].to_numpy(), sub["predicted_hour"].to_numpy())
        row = {
            "group": group_value,
            "n_windows": metrics.n,
            "mae_minutes": metrics.mae_minutes,
            "median_absolute_error_minutes": metrics.median_absolute_error_minutes,
            "rmse_minutes": metrics.rmse_minutes,
            "pct_within_30_min": metrics.pct_within_30_min,
            "pct_within_60_min": metrics.pct_within_60_min,
            "bias_minutes": metrics.signed_mean_error_minutes,
        }
        if participant_ids is not None:
            row["n_participants"] = sub["participant_id"].nunique()
        rows.append(row)

    return pd.DataFrame(rows).sort_values("group").reset_index(drop=True)


def check_success_targets(mae_minutes: float, pct_within_60_min: float, success_targets) -> str:
    """Classify overall performance against the project's (non-guaranteed)
    success targets. Returns one of: "excellent", "good", "minimum", "below_minimum".
    """

    if mae_minutes < success_targets.excellent_mae_minutes and pct_within_60_min > success_targets.excellent_pct_within_60:
        return "excellent"
    if mae_minutes < success_targets.good_mae_minutes and pct_within_60_min > success_targets.good_pct_within_60:
        return "good"
    if mae_minutes < success_targets.minimum_mae_minutes and pct_within_60_min > success_targets.minimum_pct_within_60:
        return "minimum"
    return "below_minimum"

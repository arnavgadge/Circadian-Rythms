"""Reusable window-aggregation statistics.

Every "medium signal" feature (duration/amount/ratio-type, never a raw
clock time) is built from exactly one of the functions in this module,
so there is a single place that defines what "mean over the window"
or "recency-weighted mean" actually means, rather than ad hoc
arithmetic scattered across the feature builder.

All functions accept a sequence of six values (oldest to newest, day_1
first) where a missing day is represented as ``None``, and are
consistent about what "missing" does: functions that don't need
per-day alignment (:func:`flat_mean`, :func:`flat_std`) simply ignore
``None`` entries; :func:`recency_weighted_mean`, which does need
per-day alignment (each value's weight depends on which day it is),
drops missing entries and renormalizes the remaining weights so they
still sum to 1.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from app.features.config import DEFAULT_FEATURE_CONFIG, FeatureConfig


def _present(values: Sequence[Optional[float]]) -> list:
    return [v for v in values if v is not None]


def flat_mean(values: Sequence[Optional[float]]) -> Optional[float]:
    """Arithmetic mean of the non-missing values, or ``None`` if all are missing."""

    present = _present(values)
    if not present:
        return None
    return sum(present) / len(present)


def flat_std(values: Sequence[Optional[float]]) -> Optional[float]:
    """Population standard deviation of the non-missing values.

    Returns ``0.0`` for a single present value (no variance observable)
    and ``None`` only when every value is missing.
    """

    present = _present(values)
    if not present:
        return None
    if len(present) == 1:
        return 0.0
    mean = sum(present) / len(present)
    variance = sum((v - mean) ** 2 for v in present) / len(present)
    return math.sqrt(variance)


def ratio(count_true: int, count_total: int) -> Optional[float]:
    """A simple ``count_true / count_total`` ratio, or ``None`` if there was
    nothing to count (``count_total == 0``)."""

    if count_total <= 0:
        return None
    return count_true / count_total


def recency_weighted_mean(
    values: Sequence[Optional[float]], config: FeatureConfig = DEFAULT_FEATURE_CONFIG
) -> Optional[float]:
    """Weighted mean favoring the most recent (last) values.

    ``values`` must be ordered oldest-to-newest (day_1 .. day_6), matching
    ``config.recency_weights`` (weight for day_1 first). Missing (``None``)
    entries are dropped along with their weight, and the remaining
    weights are renormalized to sum to 1 -- so a window missing its
    oldest day still produces a sensible weighted mean of what remains,
    rather than silently under-weighting toward zero.

    Returns ``None`` if every value is missing.
    """

    weights = config.recency_weights
    if len(values) != len(weights):
        raise ValueError(
            f"recency_weighted_mean expects {len(weights)} values (one per "
            f"configured weight), got {len(values)}"
        )

    paired = [(v, w) for v, w in zip(values, weights) if v is not None]
    if not paired:
        return None

    weight_sum = sum(w for _, w in paired)
    return sum(v * w for v, w in paired) / weight_sum

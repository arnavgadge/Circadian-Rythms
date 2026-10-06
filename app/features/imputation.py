"""The feature-engineering half of the Q25 missing-data architecture.

This module does **not** implement predictive imputation -- per the
brief, that is "complicated prediction logic" reserved for a later
phase. It implements exactly the documented three-tier fallback chain:

    1. compute from the window itself (the six days actually being used)
    2. **personal history**: the participant's own data from before the
       window (never from the window's target date or later -- that
       would be leakage)
    3. **population default**: a fixed, documented constant from
       :mod:`app.features.config`

and it records, for every feature, whether a value was missing and (if
so) which fallback resolved it -- nothing is silently filled in
without leaving a trace in the returned :class:`ImputationRecord`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ImputationRecord:
    """Tracks, per feature name, whether/how a value was filled in."""

    missing_features: list = field(default_factory=list)
    imputed_features: list = field(default_factory=list)
    imputation_methods: dict = field(default_factory=dict)  # name -> method string
    tier_missing_counts: dict = field(default_factory=lambda: {"tier_1": 0, "tier_2": 0, "tier_3": 0})

    def record(self, feature_name: str, tier: str, method: str) -> None:
        """Record that ``feature_name`` (in ``tier``) was missing and resolved via ``method``."""

        self.missing_features.append(feature_name)
        self.imputed_features.append(feature_name)
        self.imputation_methods[feature_name] = method
        if tier in self.tier_missing_counts:
            self.tier_missing_counts[tier] += 1


METHOD_WINDOW = "window"  # not actually a fallback: value came straight from the window
METHOD_PERSONAL_HISTORY = "personal_history"
METHOD_POPULATION_DEFAULT = "population_default"


def resolve_numeric(
    window_value: Optional[float],
    personal_history_value: Optional[float],
    population_default: float,
    feature_name: str,
    tier: str,
    record: ImputationRecord,
) -> float:
    """Resolve one numeric feature through the three-tier fallback chain."""

    if window_value is not None:
        return window_value
    if personal_history_value is not None:
        record.record(feature_name, tier, METHOD_PERSONAL_HISTORY)
        return personal_history_value
    record.record(feature_name, tier, METHOD_POPULATION_DEFAULT)
    return population_default


def resolve_circular(
    window_hour: Optional[float],
    personal_history_hour: Optional[float],
    population_default_hour: float,
    feature_name_sin: str,
    feature_name_cos: str,
    tier: str,
    record: ImputationRecord,
) -> float:
    """Resolve one circular (clock-time) feature's underlying hour value
    through the same fallback chain, then the caller encodes sin/cos.

    Both the ``_sin`` and ``_cos`` output names are recorded together
    (a missing clock time is missing for both components at once).
    """

    if window_hour is not None:
        return window_hour
    if personal_history_hour is not None:
        record.record(feature_name_sin, tier, METHOD_PERSONAL_HISTORY)
        record.record(feature_name_cos, tier, METHOD_PERSONAL_HISTORY)
        return personal_history_hour
    record.record(feature_name_sin, tier, METHOD_POPULATION_DEFAULT)
    record.record(feature_name_cos, tier, METHOD_POPULATION_DEFAULT)
    return population_default_hour

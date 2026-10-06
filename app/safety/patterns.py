"""Layer 2: persistent unusual-pattern detection.

**Not diagnosis.** Each detector below is a project screening rule
that decides whether a persistent pattern is unusual enough that
generic behavioral recommendations alone may not be the right next
step -- never a claim about a named medical condition (see
``docs/safety_and_confidence.md`` "Unusual-pattern detection").

Every detector operates only on days with ``prediction_available=True``
-- a day with no prediction is never counted as evidence for or
against a biological trend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls
from typing import Optional, Sequence

from app.safety.circular_stats import circular_mean_of_available, compute_circular_trend_minutes_per_day, signed_offset_from_midnight
from app.safety.config import DEFAULT_SAFETY_CONFIG, SafetyConfig
from app.safety.enums import (
    CONTINUOUS_DLMO_DRIFT,
    LOW_ALIGNMENT_DESPITE_COMPLIANCE,
    PERSISTENT_EARLY_PHASE,
    PERSISTENT_LATE_PHASE,
)


@dataclass(frozen=True)
class DayRecord:
    date: date_cls
    prediction_available: bool
    dlmo_hour: Optional[float] = None
    alignment_score: Optional[float] = None
    compliance_degree: Optional[float] = None


@dataclass(frozen=True)
class PatternDetectionResult:
    flag_type: str
    triggering: bool
    n_observations: int
    triggering_statistics: dict


def _available_dlmo(records: Sequence) -> list:
    return [(r.date, r.dlmo_hour) for r in records if r.prediction_available and r.dlmo_hour is not None]


def detect_persistent_late_phase(records: Sequence, config: SafetyConfig = DEFAULT_SAFETY_CONFIG) -> PatternDetectionResult:
    dated_hours = _available_dlmo(records)
    n = len(dated_hours)
    if n < config.min_observations_for_flag:
        return PatternDetectionResult(PERSISTENT_LATE_PHASE, False, n, {"reason": "insufficient_observations"})

    mean_hour = circular_mean_of_available([h for _, h in dated_hours])
    offset = signed_offset_from_midnight(mean_hour)
    threshold_offset = signed_offset_from_midnight(config.late_phase_threshold_hour)
    triggering = offset > threshold_offset

    return PatternDetectionResult(
        PERSISTENT_LATE_PHASE, triggering, n,
        {"mean_dlmo_hour": mean_hour, "threshold_hour": config.late_phase_threshold_hour, "offset": offset, "threshold_offset": threshold_offset},
    )


def detect_persistent_early_phase(records: Sequence, config: SafetyConfig = DEFAULT_SAFETY_CONFIG) -> PatternDetectionResult:
    dated_hours = _available_dlmo(records)
    n = len(dated_hours)
    if n < config.min_observations_for_flag:
        return PatternDetectionResult(PERSISTENT_EARLY_PHASE, False, n, {"reason": "insufficient_observations"})

    mean_hour = circular_mean_of_available([h for _, h in dated_hours])
    offset = signed_offset_from_midnight(mean_hour)
    threshold_offset = signed_offset_from_midnight(config.early_phase_threshold_hour)
    triggering = offset < threshold_offset

    return PatternDetectionResult(
        PERSISTENT_EARLY_PHASE, triggering, n,
        {"mean_dlmo_hour": mean_hour, "threshold_hour": config.early_phase_threshold_hour, "offset": offset, "threshold_offset": threshold_offset},
    )


def detect_continuous_drift(records: Sequence, config: SafetyConfig = DEFAULT_SAFETY_CONFIG) -> PatternDetectionResult:
    dated_hours = _available_dlmo(records)
    n = len(dated_hours)
    if n < config.min_observations_for_flag:
        return PatternDetectionResult(CONTINUOUS_DLMO_DRIFT, False, n, {"reason": "insufficient_observations"})

    trend = compute_circular_trend_minutes_per_day(dated_hours)
    triggering = trend is not None and abs(trend) > config.drift_threshold_minutes_per_day

    return PatternDetectionResult(
        CONTINUOUS_DLMO_DRIFT, triggering, n,
        {"trend_minutes_per_day": trend, "threshold_minutes_per_day": config.drift_threshold_minutes_per_day},
    )


def detect_low_alignment_despite_compliance(records: Sequence, config: SafetyConfig = DEFAULT_SAFETY_CONFIG) -> PatternDetectionResult:
    alignment_values = [r.alignment_score for r in records if r.prediction_available and r.alignment_score is not None]
    compliance_values = [r.compliance_degree for r in records if r.compliance_degree is not None]

    n = min(len(alignment_values), len(compliance_values))
    if len(alignment_values) < config.min_observations_for_flag or len(compliance_values) < config.min_observations_for_flag:
        return PatternDetectionResult(LOW_ALIGNMENT_DESPITE_COMPLIANCE, False, n, {"reason": "insufficient_observations"})

    mean_alignment = sum(alignment_values) / len(alignment_values)
    mean_compliance = sum(compliance_values) / len(compliance_values)
    triggering = mean_alignment < config.low_alignment_threshold and mean_compliance > config.high_compliance_threshold

    return PatternDetectionResult(
        LOW_ALIGNMENT_DESPITE_COMPLIANCE, triggering, n,
        {
            "mean_alignment": mean_alignment, "mean_compliance": mean_compliance,
            "alignment_threshold": config.low_alignment_threshold, "compliance_threshold": config.high_compliance_threshold,
        },
    )


def run_all_detectors(records: Sequence, config: SafetyConfig = DEFAULT_SAFETY_CONFIG) -> list:
    return [
        detect_persistent_late_phase(records, config),
        detect_persistent_early_phase(records, config),
        detect_continuous_drift(records, config),
        detect_low_alignment_despite_compliance(records, config),
    ]

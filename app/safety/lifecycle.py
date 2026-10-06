"""Flag lifecycle: DETECTED -> PERSISTING -> RESOLVED.

Resolution requires the pattern to stop triggering across
``resolution_min_normal_observations`` consecutive *available*
observations -- a single normal day never resolves an open flag (see
``docs/safety_and_confidence.md`` "Severity"/"Flag persistence").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.safety.config import DEFAULT_SAFETY_CONFIG, SafetyConfig
from app.safety.enums import DETECTED, HIGH, MODERATE, PERSISTING, RESOLVED
from app.safety.patterns import PatternDetectionResult


def determine_severity(flag_type: str, config: SafetyConfig = DEFAULT_SAFETY_CONFIG) -> str:
    return HIGH if flag_type in config.high_severity_flag_types else MODERATE


@dataclass(frozen=True)
class LifecycleDecision:
    flag_type: str
    lifecycle_state: str  # DETECTED | PERSISTING | RESOLVED
    severity: str
    triggering_statistics: dict
    n_observations: int


def reconcile_flag(
    detection: PatternDetectionResult,
    has_existing_open_flag: bool,
    resolution_check: Optional[PatternDetectionResult] = None,
    config: SafetyConfig = DEFAULT_SAFETY_CONFIG,
) -> Optional[LifecycleDecision]:
    """``resolution_check``: the same detector re-run over only the most
    recent ``resolution_min_normal_observations`` available
    observations -- required (and only consulted) when there is an
    existing open flag that is no longer triggering on the full window,
    to confirm the non-trigger is sustained rather than a single normal
    day. Returns ``None`` when there is nothing to report (never
    triggered, no open flag)."""

    severity = determine_severity(detection.flag_type, config)

    if detection.triggering:
        state = PERSISTING if has_existing_open_flag else DETECTED
        return LifecycleDecision(detection.flag_type, state, severity, detection.triggering_statistics, detection.n_observations)

    if has_existing_open_flag:
        if resolution_check is not None and not resolution_check.triggering:
            return LifecycleDecision(detection.flag_type, RESOLVED, severity, detection.triggering_statistics, detection.n_observations)
        return LifecycleDecision(detection.flag_type, PERSISTING, severity, detection.triggering_statistics, detection.n_observations)

    return None

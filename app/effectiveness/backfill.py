"""Compliance backfill: filling in ``intervention_log.compliance_binary``
/ ``compliance_degree`` / ``actual_value_*`` once the day's own
behavior becomes available.

A recommendation for day N is written by Phase 11 at the *start* of
day N, before day N's behavior exists (see
``docs/daily_inference_pipeline.md`` "Start-of-day timing") -- so
compliance can only be computed afterward, once day N's
``daily_observations`` row exists. This module is that later step; it
never recomputes or re-selects the recommendation itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.database.models import DailyObservation, InterventionLog, Recommendation
from app.effectiveness.actuals import resolve_actual_value
from app.effectiveness.compliance import ComplianceResult, evaluate_compliance, resolve_dispatch_key
from app.effectiveness.config import DEFAULT_EFFECTIVENESS_CONFIG, EffectivenessConfig
from app.recommendations.catalogue import CLOCK_HOUR, intervention_from_recommendation
from app.synthetic.time_utils import clock_time_to_hour, hour_to_clock_time


@dataclass(frozen=True)
class BackfillResult:
    compliance: ComplianceResult
    applied: bool


def backfill_compliance(
    log: InterventionLog,
    recommendation: Recommendation,
    observation: Optional[DailyObservation],
    config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG,
) -> BackfillResult:
    """Computes compliance for one ``intervention_log`` row and mutates
    it in place (``log.compliance_binary`` etc.) -- the caller commits.
    Returns the computed :class:`ComplianceResult` for inspection
    without needing a second read."""

    candidate = intervention_from_recommendation(recommendation)
    signal = resolve_dispatch_key(candidate.contributor_signals, candidate.intervention_type)

    target_value = (
        clock_time_to_hour(log.target_value_time) if log.target_value_time is not None else log.target_value_numeric
    )
    actual_sleep_onset_hour = (
        clock_time_to_hour(observation.sleep_onset_time)
        if observation is not None and observation.sleep_onset_time is not None
        else None
    )
    actual_value = resolve_actual_value(signal, observation, actual_sleep_onset_hour)

    result = evaluate_compliance(signal, target_value, actual_value, config)

    if not result.available:
        return BackfillResult(result, applied=False)

    log.compliance_binary = result.compliance_binary
    log.compliance_degree = result.compliance_degree
    if candidate.value_kind == CLOCK_HOUR:
        log.actual_value_time = hour_to_clock_time(actual_value)
    else:
        log.actual_value_numeric = actual_value

    return BackfillResult(result, applied=True)

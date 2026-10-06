"""Phase 1: compliance-adjusted observational before/after analysis.

**Labeled OBSERVATIONAL throughout** -- this compares two time periods
for the *same* participant with no control group and no adjustment for
confounds; it can show an *associated* change, never a proven causal
effect (see ``docs/intervention_effectiveness.md`` "Scientific
limitations").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls
from typing import Optional

from app.effectiveness.config import DEFAULT_EFFECTIVENESS_CONFIG, EffectivenessConfig, OBSERVATIONAL
from app.effectiveness.confound import ConfoundReport, detect_confounds
from app.effectiveness.outcomes import (
    alignment_change as _alignment_change,
    compute_all_signal_deltas,
    dlmo_change_minutes as _dlmo_change_minutes,
    period_mean_alignment_score,
    period_mean_dlmo_hour,
)
from app.effectiveness.windows import (
    INSUFFICIENT_BASELINE_HISTORY,
    INSUFFICIENT_INTERVENTION_HISTORY,
    InterventionEpisode,
    Period,
    select_baseline_window,
    select_intervention_window,
)


@dataclass(frozen=True)
class DayRecord:
    date: date_cls
    dlmo_hour: Optional[float] = None
    alignment_score: Optional[float] = None
    signal_values: dict = field(default_factory=dict)  # {signal_name: actual_value_or_None}, all 5 signals
    compliance_degree: Optional[float] = None  # only set for days within an intervention episode


@dataclass(frozen=True)
class InterventionEffectPhase1:
    intervention_id: int
    participant_id: int

    baseline_days: int
    intervention_days: int

    baseline_dlmo: Optional[float]
    recent_dlmo: Optional[float]
    dlmo_change_minutes: Optional[float]

    baseline_alignment: Optional[float]
    recent_alignment: Optional[float]
    alignment_change: Optional[float]

    compliance_rate: Optional[float]
    compliance_days: int
    observed_days: int

    effect_estimate: Optional[float]  # == dlmo_change_minutes; named per the brief's output contract
    measurement_phase: int
    interpretation: str

    confound_flag: bool
    confound_report: Optional[ConfoundReport]

    sufficient_data: bool
    insufficiency_reason: Optional[str] = None


def _insufficient(intervention_id: int, participant_id: int, reason: str) -> InterventionEffectPhase1:
    return InterventionEffectPhase1(
        intervention_id=intervention_id, participant_id=participant_id,
        baseline_days=0, intervention_days=0,
        baseline_dlmo=None, recent_dlmo=None, dlmo_change_minutes=None,
        baseline_alignment=None, recent_alignment=None, alignment_change=None,
        compliance_rate=None, compliance_days=0, observed_days=0,
        effect_estimate=None, measurement_phase=1, interpretation=OBSERVATIONAL,
        confound_flag=False, confound_report=None,
        sufficient_data=False, insufficiency_reason=reason,
    )


def _compliance_rate(
    episode: InterventionEpisode, intervention_period: Period, records: dict, config: EffectivenessConfig
) -> tuple:
    dates_in_window = [d for d in episode.log_dates if intervention_period.start_date <= d <= intervention_period.end_date]
    observed = [d for d in dates_in_window if records.get(d) is not None and records[d].compliance_degree is not None]
    compliant = [d for d in observed if records[d].compliance_degree >= config.compliance_binary_threshold]
    rate = (len(compliant) / len(observed)) if observed else None
    return rate, len(compliant), len(observed)


def evaluate_phase1_effect(
    intervention_id: int,
    participant_id: int,
    target_signal: str,
    episode: InterventionEpisode,
    records: dict,  # date -> DayRecord, covering both the baseline candidate range and the episode
    config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG,
) -> InterventionEffectPhase1:
    dlmo_available_dates = {d for d, r in records.items() if r.dlmo_hour is not None}

    baseline_period = select_baseline_window(episode.start_date, dlmo_available_dates, config)
    if baseline_period is None:
        return _insufficient(intervention_id, participant_id, INSUFFICIENT_BASELINE_HISTORY)

    intervention_period = select_intervention_window(episode, dlmo_available_dates, config)
    if intervention_period is None:
        return _insufficient(intervention_id, participant_id, INSUFFICIENT_INTERVENTION_HISTORY)

    baseline_records = [records[d] for d in baseline_period.observed_dates]
    intervention_records = [records[d] for d in intervention_period.observed_dates]

    baseline_dlmo = period_mean_dlmo_hour([r.dlmo_hour for r in baseline_records])
    recent_dlmo = period_mean_dlmo_hour([r.dlmo_hour for r in intervention_records])
    baseline_alignment = period_mean_alignment_score([r.alignment_score for r in baseline_records])
    recent_alignment = period_mean_alignment_score([r.alignment_score for r in intervention_records])

    dlmo_delta = _dlmo_change_minutes(baseline_dlmo, recent_dlmo)
    alignment_delta = _alignment_change(baseline_alignment, recent_alignment)

    compliance_rate, compliant_days, observed_days = _compliance_rate(episode, intervention_period, records, config)

    baseline_signal_values = {
        signal: [r.signal_values.get(signal) for r in baseline_records]
        for signal in ("evening_screen", "morning_light", "meal_timing", "exercise", "social_jetlag")
    }
    intervention_signal_values = {
        signal: [r.signal_values.get(signal) for r in intervention_records]
        for signal in ("evening_screen", "morning_light", "meal_timing", "exercise", "social_jetlag")
    }
    deltas = compute_all_signal_deltas(baseline_signal_values, intervention_signal_values)
    confound_report = detect_confounds(target_signal, deltas, config)

    return InterventionEffectPhase1(
        intervention_id=intervention_id,
        participant_id=participant_id,
        baseline_days=len(baseline_period.observed_dates),
        intervention_days=len(intervention_period.observed_dates),
        baseline_dlmo=baseline_dlmo,
        recent_dlmo=recent_dlmo,
        dlmo_change_minutes=dlmo_delta,
        baseline_alignment=baseline_alignment,
        recent_alignment=recent_alignment,
        alignment_change=alignment_delta,
        compliance_rate=compliance_rate,
        compliance_days=compliant_days,
        observed_days=observed_days,
        effect_estimate=dlmo_delta,
        measurement_phase=1,
        interpretation=OBSERVATIONAL,
        confound_flag=confound_report.confound_flag,
        confound_report=confound_report,
        sufficient_data=True,
    )

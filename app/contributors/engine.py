"""The contributor ranking engine: ``rank_contributors()``.

Answers two **deliberately separate** questions (never mixed):

1. "Which behavioral signals, across the recent **six-day history**,
   are contributing most to the participant's current misalignment?"
   -- the ranked ``contributors`` list.
2. "Is **today's** behavior unusually different from that six-day
   pattern?" -- the ``anomaly_details`` metadata.

The six-day ranking never reads today's values, and today's anomaly
check never influences the ranking. This engine identifies *what*
within CircadianIQ's modeled system appears to be contributing --
never a proven or medical cause, and it selects no intervention (that
is Phase 10's job).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.contributors.anomaly import AnomalyResult, detect_anomaly_circular, detect_anomaly_numeric
from app.contributors.config import DEFAULT_CONTRIBUTOR_CONFIG, ContributorConfig
from app.contributors.deficits import SIGNALS_WITHOUT_COMPONENT, compute_alignment_deficit
from app.contributors.direction import classify_direction
from app.contributors.inputs import ContributorInputs
from app.contributors.normalization import normalize_absolute_effects
from app.contributors.phase_effects import compute_window_phase_effects
from app.contributors.scoring import compute_contributor_score

SIGNALS = ("evening_screen", "morning_light", "meal_timing", "social_jetlag", "exercise")


@dataclass(frozen=True)
class Contributor:
    signal: str
    rank: int
    signed_phase_effect_minutes: Optional[float]
    absolute_phase_effect_minutes: Optional[float]
    normalized_phase_effect: Optional[float]
    alignment_component_score: Optional[float]
    alignment_deficit: Optional[float]
    contributor_score: Optional[float]
    direction: str
    significant: bool
    today_anomaly: Optional[bool]
    data_quality: str  # "observed" | "imputed" | "unavailable"
    weight_used: str


@dataclass(frozen=True)
class ContributorResult:
    contributors: list  # top 3 (or fewer if fewer valid signals exist)
    all_candidates: list  # all computed signals, ranked, for transparency/diagnostics
    history_days_used: int
    baseline_date_range: Optional[tuple]
    anomaly_details: dict  # signal -> AnomalyResult
    ranking_method_version: str


def _data_quality(days_used: int, days_available: int) -> str:
    if days_available == 0:
        return "unavailable"
    if days_used < days_available:
        return "imputed"  # some window days were skipped for missing raw data
    return "observed"


def rank_contributors(
    inputs: ContributorInputs, config: ContributorConfig = DEFAULT_CONTRIBUTOR_CONFIG
) -> ContributorResult:
    phase_effects = compute_window_phase_effects(
        inputs.traits,
        inputs.window_morning_light_duration_minutes,
        inputs.window_evening_screen_duration_hours,
        inputs.window_last_meal_hours,
        inputs.window_exercise_hours,
    )

    absolute_effects = {
        name: (abs(e.mean_signed_effect_minutes) if e.mean_signed_effect_minutes is not None else None)
        for name, e in phase_effects.items()
    }
    normalized_effects = normalize_absolute_effects(absolute_effects, config.zero_effect_epsilon)

    phase_deviation = inputs.alignment_result.phase_difference_minutes

    candidates: list[Contributor] = []
    anomaly_details: dict = {}

    for signal in SIGNALS:
        effect = phase_effects.get(signal)
        signed_effect = effect.mean_signed_effect_minutes if effect else None
        absolute_effect = absolute_effects.get(signal)
        normalized_effect = normalized_effects.get(signal)

        component_name = None
        component_score = None
        if signal not in SIGNALS_WITHOUT_COMPONENT:
            component = inputs.alignment_result.behavioral_components.get(
                {"evening_screen": "evening_screen", "morning_light": "morning_light",
                 "meal_timing": "meal_timing", "social_jetlag": "social_jetlag"}.get(signal)
            )
            if component is not None and component.available:
                component_score = component.score
        alignment_deficit = compute_alignment_deficit(signal, inputs.alignment_result)

        score_result = compute_contributor_score(signal, normalized_effect, alignment_deficit, config)
        contributor_score = score_result.contributor_score

        significant = contributor_score is not None and contributor_score >= config.significance_threshold
        direction = classify_direction(signed_effect, phase_deviation, contributor_score, config)

        if effect is not None:
            data_quality = _data_quality(effect.days_used, effect.days_available)
        else:
            data_quality = "observed" if alignment_deficit is not None else "unavailable"

        anomaly = _compute_anomaly_for_signal(signal, inputs, config)
        anomaly_details[signal] = anomaly

        candidates.append(
            Contributor(
                signal=signal,
                rank=0,  # assigned after sorting
                signed_phase_effect_minutes=signed_effect,
                absolute_phase_effect_minutes=absolute_effect,
                normalized_phase_effect=normalized_effect,
                alignment_component_score=component_score,
                alignment_deficit=alignment_deficit,
                contributor_score=contributor_score,
                direction=direction,
                significant=significant,
                today_anomaly=anomaly.is_anomaly if anomaly.available else None,
                data_quality=data_quality,
                weight_used=score_result.weight_used,
            )
        )

    valid = [c for c in candidates if c.contributor_score is not None]
    valid.sort(key=lambda c: c.contributor_score, reverse=True)
    ranked_all = valid + [c for c in candidates if c.contributor_score is None]
    for i, c in enumerate(valid, start=1):
        ranked_all[i - 1] = _with_rank(c, i)

    top_3 = ranked_all[: min(3, len(valid))]

    baseline_range = None
    if inputs.window_dates:
        dates = [d for d in inputs.window_dates if d is not None]
        if dates:
            baseline_range = (min(dates), max(dates))

    return ContributorResult(
        contributors=top_3,
        all_candidates=ranked_all,
        history_days_used=max((e.days_used for e in phase_effects.values()), default=0),
        baseline_date_range=baseline_range,
        anomaly_details=anomaly_details,
        ranking_method_version=config.contributor_config_version,
    )


def _with_rank(contributor: Contributor, rank: int) -> Contributor:
    return Contributor(
        signal=contributor.signal, rank=rank,
        signed_phase_effect_minutes=contributor.signed_phase_effect_minutes,
        absolute_phase_effect_minutes=contributor.absolute_phase_effect_minutes,
        normalized_phase_effect=contributor.normalized_phase_effect,
        alignment_component_score=contributor.alignment_component_score,
        alignment_deficit=contributor.alignment_deficit,
        contributor_score=contributor.contributor_score,
        direction=contributor.direction, significant=contributor.significant,
        today_anomaly=contributor.today_anomaly, data_quality=contributor.data_quality,
        weight_used=contributor.weight_used,
    )


def _hours_to_minutes(value):
    return value * 60.0 if value is not None else None


def _compute_anomaly_for_signal(signal: str, inputs: ContributorInputs, config: ContributorConfig) -> AnomalyResult:
    if signal == "evening_screen":
        # Screen duration is stored in hours; the anomaly detector's
        # fallback threshold and modified-z deviations are denominated
        # in minutes throughout this module, so convert here rather
        # than silently comparing hours against a minutes threshold.
        return detect_anomaly_numeric(
            signal,
            _hours_to_minutes(inputs.latest_evening_screen_duration_hours),
            [_hours_to_minutes(v) for v in inputs.window_evening_screen_duration_hours],
            config,
        )
    if signal == "morning_light":
        return detect_anomaly_numeric(
            signal, inputs.latest_morning_light_duration_minutes,
            inputs.window_morning_light_duration_minutes, config,
        )
    if signal == "meal_timing":
        return detect_anomaly_circular(signal, inputs.latest_last_meal_hour, inputs.window_last_meal_hours, config)
    if signal == "exercise":
        return detect_anomaly_circular(signal, inputs.latest_exercise_hour, inputs.window_exercise_hours, config)
    if signal == "social_jetlag":
        return detect_anomaly_numeric(
            signal, inputs.latest_social_jetlag_minutes, inputs.window_social_jetlag_minutes, config
        )
    raise ValueError(f"Unknown signal: {signal}")

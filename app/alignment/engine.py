"""The top-level alignment engine: ``compute_alignment()``.

Combines phase alignment (60%) and behavioral alignment (40%) into the
final 0-100 alignment score. Pure computation: no database access, no
XGBoost, no state-engine transition logic -- only the already-fused
DLMO (Phase 7's output) and the participant's actual behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.alignment.behavioral_alignment import BehavioralAlignmentResult, compute_behavioral_alignment
from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG, AlignmentConfig
from app.alignment.inputs import AlignmentInputs, ComponentScore
from app.alignment.phase_alignment import PhaseAlignmentResult, compute_phase_alignment

_TOTAL_SLOTS = 6  # phase + 5 behavioral components


@dataclass(frozen=True)
class AlignmentResult:
    final_score: float
    phase_score: float
    behavioral_score: float

    ideal_sleep_onset_hour: float
    actual_sleep_onset_hour: float | None
    phase_difference_minutes: float | None

    behavioral_components: dict  # name -> ComponentScore

    data_completeness: float
    imputed_components: list

    diagnostics: dict


def _most_recent_available(values: list):
    for value in reversed(values):
        if value is not None:
            return value
    return None


def compute_alignment(
    inputs: AlignmentInputs, config: AlignmentConfig = DEFAULT_ALIGNMENT_CONFIG
) -> AlignmentResult:
    config.validate()

    fallback_onset = _most_recent_available(inputs.window_sleep_onset_hours)
    phase_result: PhaseAlignmentResult = compute_phase_alignment(
        inputs.fused_dlmo_hour, inputs.most_recent_sleep_onset_hour, fallback_onset, config
    )

    behavioral_result: BehavioralAlignmentResult = compute_behavioral_alignment(inputs, config)

    final_score = (
        config.phase_alignment_weight * phase_result.phase_score
        + config.behavioral_alignment_weight * behavioral_result.behavioral_score
    )
    final_score = max(0.0, min(100.0, final_score))

    imputed_components = []
    if phase_result.imputed or not phase_result.available:
        imputed_components.append("phase")
    for name, component in behavioral_result.components.items():
        if component.imputed or not component.available:
            imputed_components.append(name)

    fully_observed = _TOTAL_SLOTS - len(imputed_components)
    data_completeness = fully_observed / _TOTAL_SLOTS

    return AlignmentResult(
        final_score=final_score,
        phase_score=phase_result.phase_score,
        behavioral_score=behavioral_result.behavioral_score,
        ideal_sleep_onset_hour=phase_result.ideal_sleep_onset_hour,
        actual_sleep_onset_hour=phase_result.actual_sleep_onset_hour,
        phase_difference_minutes=phase_result.phase_deviation_minutes,
        behavioral_components=behavioral_result.components,
        data_completeness=data_completeness,
        imputed_components=imputed_components,
        diagnostics={
            "phase_available": phase_result.available,
            "phase_imputed": phase_result.imputed,
            "phase_notes": phase_result.notes,
            "config_version": config.alignment_config_version,
        },
    )

"""The measurement-phase dispatcher: ``evaluate_intervention_effect()``.

Chooses the **highest valid** measurement phase for which sufficient
data actually exists -- never jumps to a stronger-sounding phase just
because it would be more interesting; Phase 3 is only reported when
its own regression sample-size gate is met, and Phase 2 only when its
own matching gate is met, independent of whether a later phase also
happened to succeed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.effectiveness.config import DEFAULT_EFFECTIVENESS_CONFIG, EffectivenessConfig
from app.effectiveness.outcomes import period_mean_dlmo_hour
from app.effectiveness.phase1 import DayRecord, InterventionEffectPhase1, evaluate_phase1_effect
from app.effectiveness.phase2 import InterventionEffectPhase2, evaluate_phase2_effect
from app.effectiveness.phase3 import InterventionEffectPhase3, evaluate_phase3_effect
from app.effectiveness.windows import InterventionEpisode, select_intervention_window


@dataclass(frozen=True)
class InterventionEffectResult:
    chosen_phase: Optional[int]  # None if even Phase 1 lacks sufficient data
    phase1: InterventionEffectPhase1
    phase2: Optional[InterventionEffectPhase2]
    phase3: Optional[InterventionEffectPhase3]


def evaluate_intervention_effect(
    intervention_id: int,
    participant_id: int,
    target_signal: str,
    episode: InterventionEpisode,
    records: dict,  # date -> DayRecord, spanning the participant's FULL history for this intervention_id
    config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG,
) -> InterventionEffectResult:
    phase1 = evaluate_phase1_effect(intervention_id, participant_id, target_signal, episode, records, config)

    if not phase1.sufficient_data:
        return InterventionEffectResult(chosen_phase=None, phase1=phase1, phase2=None, phase3=None)

    chosen_phase = 1
    phase2: Optional[InterventionEffectPhase2] = None
    phase3: Optional[InterventionEffectPhase3] = None

    if len(records) >= config.min_history_days_for_phase2:
        dlmo_available_dates = {d for d, r in records.items() if r.dlmo_hour is not None}
        intervention_period = select_intervention_window(episode, dlmo_available_dates, config)
        if intervention_period is not None:
            phase2 = evaluate_phase2_effect(intervention_id, participant_id, target_signal, records, intervention_period, config)
            if phase2.sufficient_data:
                chosen_phase = 2

    baseline_reference = phase1.baseline_dlmo
    if baseline_reference is None:
        baseline_reference = period_mean_dlmo_hour([r.dlmo_hour for r in records.values()])

    if baseline_reference is not None:
        phase3 = evaluate_phase3_effect(intervention_id, participant_id, records, baseline_reference, config)
        if phase3.sufficient_data:
            chosen_phase = 3

    return InterventionEffectResult(chosen_phase=chosen_phase, phase1=phase1, phase2=phase2, phase3=phase3)

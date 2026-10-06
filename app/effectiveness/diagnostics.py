"""The Phase 12 effectiveness diagnostic report builder.

Summarizes a batch of :class:`~app.effectiveness.dispatcher.InterventionEffectResult`
objects, each carrying (in the controlled simulation harness) a known
``true_effect_minutes`` for error-against-ground-truth reporting.
**Only the simulation harness knows the true effect** -- the
effectiveness system itself never sees it; this module is the one
place that is allowed to compare the two, and only for diagnostic
reporting, never as an input to estimation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class DiagnosticRun:
    result: object  # InterventionEffectResult
    true_effect_minutes: Optional[float] = None  # only known because this is a controlled synthetic harness


def summarize_effectiveness_batch(runs: list) -> dict:
    phase_counts = {1: 0, 2: 0, 3: 0, None: 0}
    compliance_rates = []
    dlmo_changes = []
    alignment_changes = []
    confound_count = 0
    errors_vs_ground_truth = []

    for run in runs:
        result = run.result
        phase_counts[result.chosen_phase] = phase_counts.get(result.chosen_phase, 0) + 1

        p1 = result.phase1
        if p1.compliance_rate is not None:
            compliance_rates.append(p1.compliance_rate)
        if p1.dlmo_change_minutes is not None:
            dlmo_changes.append(p1.dlmo_change_minutes)
        if p1.alignment_change is not None:
            alignment_changes.append(p1.alignment_change)
        if p1.confound_flag:
            confound_count += 1

        if run.true_effect_minutes is not None:
            if result.chosen_phase == 3 and result.phase3.effect_mins_per_compliance_unit is not None:
                errors_vs_ground_truth.append(abs(result.phase3.effect_mins_per_compliance_unit - run.true_effect_minutes))
            elif result.chosen_phase in (1, 2):
                estimate = p1.effect_estimate if result.chosen_phase == 1 else result.phase2.mean_dlmo_difference
                if estimate is not None:
                    errors_vs_ground_truth.append(abs(estimate - run.true_effect_minutes))

    def _mean(values):
        return sum(values) / len(values) if values else None

    return {
        "n_runs": len(runs),
        "phase_distribution": {str(k): v for k, v in phase_counts.items()},
        "mean_compliance_rate": _mean(compliance_rates),
        "mean_observed_dlmo_change_minutes": _mean(dlmo_changes),
        "mean_observed_alignment_change": _mean(alignment_changes),
        "confound_frequency": confound_count / len(runs) if runs else None,
        "mean_absolute_error_vs_known_synthetic_ground_truth": _mean(errors_vs_ground_truth),
        "n_estimates_compared_to_ground_truth": len(errors_vs_ground_truth),
    }

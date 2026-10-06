"""The Phase 13 personalization diagnostic report builder.

**All distributions here are properties of the controlled synthetic
harness / simulated bandit environment used to produce them** -- never
evidence about real participants or real intervention effectiveness
(see ``docs/personalization_engine.md`` "Synthetic-data warning").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PhaseSnapshot:
    as_of_label: str
    participant_id: int
    intervention_type: str
    phase: str
    n_observations: int


@dataclass
class BanditSimulationResult:
    n_rounds: int
    selection_counts: dict
    posterior_history: dict  # intervention_type -> list of (round, mean, variance)
    true_means: dict


def summarize_phase_snapshots(snapshots: list) -> dict:
    phase_distribution: dict = {}
    phase_by_type: dict = {}

    for snap in snapshots:
        phase_distribution[snap.phase] = phase_distribution.get(snap.phase, 0) + 1
        phase_by_type.setdefault(snap.intervention_type, {})
        phase_by_type[snap.intervention_type][snap.phase] = phase_by_type[snap.intervention_type].get(snap.phase, 0) + 1

    return {
        "n_snapshots": len(snapshots),
        "phase_distribution": phase_distribution,
        "phase_distribution_by_intervention_type": phase_by_type,
    }


def summarize_bandit_simulation(result: BanditSimulationResult) -> dict:
    final_posteriors = {
        itype: history[-1][1] if history else None for itype, history in result.posterior_history.items()
    }
    return {
        "n_rounds": result.n_rounds,
        "true_means": result.true_means,
        "selection_counts": result.selection_counts,
        "selection_frequency": {k: v / result.n_rounds for k, v in result.selection_counts.items()},
        "final_posterior_means": final_posteriors,
        "favors_higher_true_mean_arm": (
            max(result.selection_counts, key=result.selection_counts.get) == max(result.true_means, key=result.true_means.get)
        ),
    }

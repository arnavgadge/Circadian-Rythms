"""Feasibility: a structured, deliberately simple 0-1 estimate of how
achievable a candidate intervention's graduated target is for this
participant right now.

Combines (see ``docs/recommendation_engine.md`` "Impact/feasibility
weighting" for the full rationale):

1. the catalogue's ``baseline_feasibility`` (a project default, not a
   measured quantity),
2. a pull toward/away from that baseline based on the participant's
   recent compliance rate with this same intervention, where history
   exists,
3. a penalty proportional to how large a fraction of the
   intervention's own allowed shift the graduated target actually
   uses (a bigger ask is harder to sustain),
4. a flat penalty if the same intervention was recently logged as
   non-compliant.

This is intentionally not fit to data (no overfitting) -- it is a
transparent, configurable heuristic, superseded by the effectiveness/
personalization phases' own feasibility learning later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from app.recommendations.config import DEFAULT_RECOMMENDATION_CONFIG, RecommendationConfig


@dataclass(frozen=True)
class RecentComplianceRecord:
    """One prior ``intervention_log`` row's compliance outcome for the
    same intervention, within the configured lookback window."""

    compliance_binary: Optional[bool]
    compliance_degree: Optional[float]  # 0-1, finer-grained than the binary flag


@dataclass(frozen=True)
class FeasibilityResult:
    score: float  # 0-1
    basis: str  # human-readable summary of which factors were applied


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def compute_feasibility(
    baseline_feasibility: float,
    shift_fraction_of_bound: float,  # |applied_shift| / max_shift_per_recommendation, already clipped to [0,1]
    recent_compliance: Sequence[RecentComplianceRecord] = (),
    config: RecommendationConfig = DEFAULT_RECOMMENDATION_CONFIG,
) -> FeasibilityResult:
    score = baseline_feasibility
    notes = [f"baseline={baseline_feasibility:.2f}"]

    degrees = [
        (1.0 if r.compliance_binary else 0.0) if r.compliance_degree is None else r.compliance_degree
        for r in recent_compliance
    ]
    if degrees:
        compliance_rate = sum(degrees) / len(degrees)
        adjustment = config.compliance_feasibility_weight * (compliance_rate - 0.5) * 2.0
        score += adjustment
        notes.append(f"compliance_rate={compliance_rate:.2f} (adj={adjustment:+.2f})")

    difficulty_penalty = config.target_difficulty_feasibility_weight * shift_fraction_of_bound
    score -= difficulty_penalty
    notes.append(f"difficulty_penalty=-{difficulty_penalty:.2f}")

    recent_failure = any(r.compliance_binary is False for r in recent_compliance)
    if recent_failure:
        score -= config.recent_failure_feasibility_penalty
        notes.append(f"recent_failure_penalty=-{config.recent_failure_feasibility_penalty:.2f}")

    return FeasibilityResult(score=_clamp01(score), basis="; ".join(notes))

"""The transparent candidate-scoring equation.

    candidate_score =
        contributor_relevance
        * (impact_weight * normalized_expected_impact + feasibility_weight * normalized_feasibility)
        + personalization_score_adjustment
        + continuation_bonus (if applicable -- see app.recommendations.cooldown)

``impact_weight`` / ``feasibility_weight`` come from the participant's
current misalignment severity (``app.recommendations.severity``).
``normalized_expected_impact`` and ``normalized_feasibility`` are both
max-scaled to ``[0, 1]`` across the candidate set being compared, the
same transparent normalization pattern Phase 9 uses -- never a hidden
or opaque combination.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CandidateScore:
    candidate_score: float
    contributor_relevance: float
    normalized_expected_impact: float
    normalized_feasibility: float
    personalization_score_adjustment: float
    continuation_bonus_applied: float


def normalize_max_scale(values: dict, epsilon: float = 1e-9) -> dict:
    """``signal -> magnitude`` -> ``signal -> magnitude / max(magnitude)``,
    the same max-scaling normalization used throughout
    ``app.contributors`` -- the single largest value in the set becomes
    1.0. All-zero (or empty) input normalizes to all zeros rather than
    dividing by zero."""

    present = {k: v for k, v in values.items() if v is not None}
    max_value = max(present.values()) if present else 0.0

    if max_value <= epsilon:
        return {k: (0.0 if v is not None else None) for k, v in values.items()}
    return {k: (v / max_value if v is not None else None) for k, v in values.items()}


def compute_candidate_score(
    contributor_relevance: float,
    normalized_expected_impact: float,
    normalized_feasibility: float,
    impact_weight: float,
    feasibility_weight: float,
    personalization_score_adjustment: float = 0.0,
    continuation_bonus: float = 0.0,
) -> CandidateScore:
    base = contributor_relevance * (
        impact_weight * normalized_expected_impact + feasibility_weight * normalized_feasibility
    )
    total = base + personalization_score_adjustment + continuation_bonus

    return CandidateScore(
        candidate_score=total,
        contributor_relevance=contributor_relevance,
        normalized_expected_impact=normalized_expected_impact,
        normalized_feasibility=normalized_feasibility,
        personalization_score_adjustment=personalization_score_adjustment,
        continuation_bonus_applied=continuation_bonus,
    )

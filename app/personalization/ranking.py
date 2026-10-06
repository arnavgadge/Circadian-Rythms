"""Phase 1: personal ranking.

    personal_score = |personal_effect_estimate| x compliance_probability

Magnitude, not signed value -- matches Phase 10's own convention of
treating ``expected_improvement_minutes`` as a magnitude (direction is
Phase 8/9's job, not the ranking score's). Personal effect evidence is
**consumed** from Phase 12's already-computed
``intervention_effect_estimates`` row -- never recalculated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from app.personalization.compliance_probability import estimate_compliance_probability
from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG, PersonalizationConfig
from app.personalization.phases import classify_evidence_strength

_PHASE_SOURCE_LABELS = {1: "phase1_observational", 2: "phase2_matched_observational", 3: "phase3_regression"}


@dataclass(frozen=True)
class PersonalRankingEntry:
    intervention_type: str
    personal_effect: Optional[float]
    compliance_probability: Optional[float]
    personal_score: Optional[float]
    evidence_count: int
    evidence_strength: str
    evidence_source: str  # "literature" | "phase1_observational" | "phase2_matched_observational" | "phase3_regression"


def compute_personal_ranking_entry(
    intervention_type: str,
    literature_effect: Optional[float],
    effect_estimate_measurement_phase: Optional[int],
    effect_estimate_value: Optional[float],
    n_observations: int,
    historical_compliance_degrees: Sequence,
    config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG,
) -> PersonalRankingEntry:
    evidence_strength = classify_evidence_strength(n_observations, config)
    compliance_probability = estimate_compliance_probability(historical_compliance_degrees)

    has_sufficient_evidence = n_observations >= config.ranking_min_observations and effect_estimate_value is not None
    if has_sufficient_evidence:
        personal_effect = effect_estimate_value
        evidence_source = _PHASE_SOURCE_LABELS.get(effect_estimate_measurement_phase, "phase1_observational")
    else:
        personal_effect = literature_effect
        evidence_source = "literature"

    personal_score = (
        abs(personal_effect) * compliance_probability if personal_effect is not None and compliance_probability is not None else None
    )

    return PersonalRankingEntry(
        intervention_type=intervention_type,
        personal_effect=personal_effect,
        compliance_probability=compliance_probability,
        personal_score=personal_score,
        evidence_count=n_observations,
        evidence_strength=evidence_strength,
        evidence_source=evidence_source,
    )


def rank_candidates(entries: Sequence) -> list:
    """Descending by ``personal_score``; entries with no computable
    score sort last rather than being dropped (so an unrankable
    candidate can still be shown, just never preferred)."""

    return sorted(entries, key=lambda e: (e.personal_score is not None, e.personal_score or 0.0), reverse=True)

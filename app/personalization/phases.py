"""Personalization-phase graduation: ``get_personalization_phase()``.

Reuses the exact phase constants Phase 10's recommendation engine
already defines (``app.recommendations.personalization``) -- Phase 13
does not invent a second, parallel phase enum. Graduation is decided
**independently per intervention type** from actual accumulated
evidence (observation count + weeks active), never assigned once for
the whole participant.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG, PersonalizationConfig
from app.recommendations.personalization import ADAPTIVE_POLICY, LITERATURE, PERSONAL_EFFECT, PERSONAL_RANKING

EVIDENCE_INSUFFICIENT = "insufficient"
EVIDENCE_WEAK = "weak"
EVIDENCE_EMERGING = "emerging"
EVIDENCE_MODERATE = "moderate"
EVIDENCE_STRONGER = "stronger"


@dataclass(frozen=True)
class EvidenceSummary:
    intervention_type: str
    n_observations: int
    weeks_active: float
    evidence_strength: str


def classify_evidence_strength(n_observations: int, config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG) -> str:
    if n_observations <= config.evidence_insufficient_max:
        return EVIDENCE_INSUFFICIENT
    if n_observations <= config.evidence_weak_max:
        return EVIDENCE_WEAK
    if n_observations <= config.evidence_emerging_max:
        return EVIDENCE_EMERGING
    if n_observations <= config.evidence_moderate_max:
        return EVIDENCE_MODERATE
    return EVIDENCE_STRONGER


def phase_from_evidence(
    n_observations: int, weeks_active: float, config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG
) -> str:
    """The highest phase for which **both** the observation-count and
    weeks-active gates are met -- data availability decides this, never
    a preference or a model's own confidence. Each intervention type
    is graduated independently by calling this once per type. The
    DB-aware convenience wrapper matching the brief's
    ``get_personalization_phase(participant, intervention_type)`` is
    ``app.personalization.dispatcher.get_personalization_phase``."""

    if n_observations >= config.adaptive_min_observations and weeks_active >= config.adaptive_min_weeks_active:
        return ADAPTIVE_POLICY
    if n_observations >= config.effect_model_min_observations and weeks_active >= config.effect_model_min_weeks_active:
        return PERSONAL_EFFECT
    if n_observations >= config.ranking_min_observations and weeks_active >= config.ranking_min_weeks_active:
        return PERSONAL_RANKING
    return LITERATURE

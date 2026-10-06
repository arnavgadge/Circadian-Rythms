"""The Phase 13 personalization dispatcher -- the two public entry
points named in the brief:

    get_personalization_phase(participant_id, intervention_type)
    personalize_recommendations(participant_id, candidate_interventions, ...)

Read-only against already-persisted state (`intervention_log`,
`intervention_effect_estimates`) -- this module never recomputes
Phase 12 effectiveness itself; see ``app.personalization.update`` for
the separate, offline pipeline that does that and writes
``personal_effect_models``.

**Boundary with Phase 10** (see docs "Recommendation-engine
integration"): this module answers "here is the personalized evidence
for each candidate"; it does not choose primary/supporting or apply
any of Phase 10's own constraints. Its output feeds directly into
``app.recommendations.inputs.RecommendationInputs`` fields that already
existed for exactly this purpose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls
from typing import Optional, Sequence

from app.personalization.blending import blend_effect
from app.personalization.compliance_probability import estimate_compliance_probability
from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG, PersonalizationConfig
from app.personalization.db_adapter import (
    count_compliance_observations,
    historical_compliance_values,
    latest_effect_estimate,
    weeks_active_for_type,
)
from app.personalization.effect_model import PersonalEffectModelResult, build_personal_effect_model, predict_effect
from app.personalization.explain import explain_adaptive, explain_literature, explain_personal_effect, explain_personal_ranking
from app.personalization.phases import EvidenceSummary, classify_evidence_strength, phase_from_evidence
from app.personalization.ranking import PersonalRankingEntry, compute_personal_ranking_entry
from app.recommendations.catalogue import CandidateIntervention
from app.recommendations.personalization import ADAPTIVE_POLICY, LITERATURE, PERSONAL_EFFECT, PERSONAL_RANKING


def get_personalization_phase(
    session, participant_id: int, intervention_type: str, as_of_date: date_cls,
    config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG,
) -> str:
    """The brief's exact ``get_personalization_phase(participant, intervention_type)``
    -- graduation is decided independently for this one intervention
    type, from evidence strictly before ``as_of_date``."""

    n_observations = count_compliance_observations(session, participant_id, intervention_type, as_of_date)
    weeks_active = weeks_active_for_type(session, participant_id, intervention_type, as_of_date)
    return phase_from_evidence(n_observations, weeks_active, config)


def get_evidence_summary(
    session, participant_id: int, intervention_type: str, as_of_date: date_cls,
    config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG,
) -> EvidenceSummary:
    n_observations = count_compliance_observations(session, participant_id, intervention_type, as_of_date)
    weeks_active = weeks_active_for_type(session, participant_id, intervention_type, as_of_date)
    return EvidenceSummary(intervention_type, n_observations, weeks_active, classify_evidence_strength(n_observations, config))


@dataclass(frozen=True)
class PersonalizationOutput:
    phase_by_intervention_type: dict
    effective_personalization_phase: str  # what to pass to RecommendationInputs.personalization_phase
    personalized_ranking: dict  # intervention_id -> normalized score adjustment
    personal_expected_improvement: dict  # intervention_id -> minutes
    ranking_entries: dict  # intervention_type -> PersonalRankingEntry
    effect_models: dict  # intervention_type -> PersonalEffectModelResult
    explanations: dict  # intervention_id -> str


def personalize_recommendations(
    session,
    participant_id: int,
    candidate_interventions: Sequence[CandidateIntervention],
    as_of_date: date_cls,
    config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG,
) -> PersonalizationOutput:
    phase_by_type: dict = {}
    ranking_entries: dict = {}
    effect_models: dict = {}
    personalized_ranking: dict = {}
    personal_expected_improvement: dict = {}
    explanations: dict = {}

    for candidate in candidate_interventions:
        itype = candidate.intervention_type

        if itype not in phase_by_type:
            phase_by_type[itype] = get_personalization_phase(session, participant_id, itype, as_of_date, config)
        phase = phase_by_type[itype]

        if phase == LITERATURE:
            explanations[candidate.intervention_id] = explain_literature()
            continue

        n_observations = count_compliance_observations(session, participant_id, itype, as_of_date)
        compliance_values = historical_compliance_values(session, participant_id, itype, as_of_date)
        estimate_row = latest_effect_estimate(session, participant_id, itype, as_of_date)

        if itype not in ranking_entries:
            ranking_entries[itype] = compute_personal_ranking_entry(
                itype, candidate.literature_expected_improvement_minutes,
                estimate_row.measurement_phase if estimate_row is not None else None,
                estimate_row.effect_estimate if estimate_row is not None else None,
                n_observations, compliance_values, config,
            )
        entry = ranking_entries[itype]

        if phase == PERSONAL_RANKING:
            if entry.personal_score is not None:
                # Compressed toward [0, 1] so this additive adjustment
                # stays commensurate with Phase 10's own 0-1-scaled
                # score terms -- a raw minutes*probability value would
                # otherwise dominate the sum arbitrarily.
                personalized_ranking[candidate.intervention_id] = min(
                    1.0, entry.personal_score / config.max_plausible_effect_minutes
                )
            explanations[candidate.intervention_id] = explain_personal_ranking()
            continue

        # PERSONAL_EFFECT or ADAPTIVE_POLICY: both consume the fitted
        # personal-effect curve (Phase 10 has no separate adaptive
        # expected-improvement channel yet -- see module docstring).
        if itype not in effect_models:
            effect_models[itype] = build_personal_effect_model(itype, estimate_row, compliance_values, config)
        model = effect_models[itype]

        personal_point_estimate = predict_effect(model.slope, model.intercept, 1.0) if model.validity.valid else None
        blended = blend_effect(
            candidate.literature_expected_improvement_minutes, personal_point_estimate, n_observations, model.validity.valid, config
        )
        if blended.value is not None:
            personal_expected_improvement[candidate.intervention_id] = blended.value

        explanations[candidate.intervention_id] = (
            explain_adaptive() if phase == ADAPTIVE_POLICY else explain_personal_effect(itype)
        )

    if personal_expected_improvement:
        effective_phase = PERSONAL_EFFECT
    elif personalized_ranking:
        effective_phase = PERSONAL_RANKING
    else:
        effective_phase = LITERATURE

    return PersonalizationOutput(
        phase_by_intervention_type=phase_by_type,
        effective_personalization_phase=effective_phase,
        personalized_ranking=personalized_ranking,
        personal_expected_improvement=personal_expected_improvement,
        ranking_entries=ranking_entries,
        effect_models=effect_models,
        explanations=explanations,
    )

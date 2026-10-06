"""The Phase 13 personalization **update pipeline** -- a separate,
offline process from daily inference:

    intervention history
        -> Phase 12 effectiveness evidence (evaluate + persist)
        -> personal-effect model refresh
        -> phase determination
        -> personal_effect_models upsert

Daily inference (Phase 11) only ever *reads* the resulting state via
``app.personalization.dispatcher`` -- it never triggers this pipeline
itself. Refresh only happens when there is a deterministic reason to
(new compliance evidence since the last stored model), never on every
trivial row, and never creating an unbounded number of model rows
(``personal_effect_models`` is upserted in place; the auditable
history of *how the estimate got there* is Phase 12's immutable
``intervention_effect_estimates`` log, not a second versioned copy
here).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional

from app.database.models import PersonalEffectModel
from app.effectiveness.db_adapter import load_episodes, load_intervention_records, load_target_signal
from app.effectiveness.dispatcher import evaluate_intervention_effect
from app.effectiveness.persistence import persist_effect_estimate
from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG, PersonalizationConfig
from app.personalization.db_adapter import (
    count_compliance_observations,
    latest_recommendation_id_for_type,
    load_personal_effect_model,
    weeks_active_for_type,
)
from app.personalization.effect_model import build_personal_effect_model
from app.personalization.phases import phase_from_evidence

NO_ACTIVE_RECOMMENDATION = "no_active_recommendation"
NO_EPISODE_HISTORY = "no_episode_history"
REFRESH_NOT_DUE = "refresh_not_due"
UPDATED = "updated"


@dataclass(frozen=True)
class UpdateOutcome:
    status: str  # one of the module-level constants above
    intervention_type: str
    personal_effect_model: Optional[PersonalEffectModel] = None


def _refresh_is_due(existing: Optional[PersonalEffectModel], current_n_observations: int, config: PersonalizationConfig) -> bool:
    if existing is None:
        return True
    return (current_n_observations - existing.num_observations) >= config.min_new_observations_for_refresh


def update_personalization_state(
    session,
    participant_id: int,
    intervention_type: str,
    as_of_date: date_cls,
    config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG,
) -> UpdateOutcome:
    """Runs Phase 12 evaluation for this participant/intervention-type's
    currently-active catalogue entry, persists it, and (only if
    warranted) upserts ``personal_effect_models``. Commits the
    session -- callers running this as a batch job should call once
    per participant/type and let each call be its own unit of work."""

    recommendation_id = latest_recommendation_id_for_type(session, intervention_type)
    if recommendation_id is None:
        return UpdateOutcome(NO_ACTIVE_RECOMMENDATION, intervention_type)

    # as_of_date-scoped throughout: this pipeline must reconstruct only
    # what was knowable strictly before as_of_date (see
    # app.personalization.db_adapter's temporal-leakage-prevention
    # contract, which this offline pipeline must uphold too even though
    # its own reads go through app.effectiveness.db_adapter instead).
    episodes = load_episodes(session, participant_id, recommendation_id, as_of_date=as_of_date)
    if not episodes:
        return UpdateOutcome(NO_EPISODE_HISTORY, intervention_type)

    current_n_observations = count_compliance_observations(session, participant_id, intervention_type, as_of_date)
    existing = load_personal_effect_model(session, participant_id, intervention_type)
    if not _refresh_is_due(existing, current_n_observations, config):
        return UpdateOutcome(REFRESH_NOT_DUE, intervention_type, existing)

    target_signal = load_target_signal(session, recommendation_id)
    episode = episodes[-1]
    records = load_intervention_records(session, participant_id, recommendation_id, as_of_date=as_of_date)

    result = evaluate_intervention_effect(recommendation_id, participant_id, target_signal, episode, records)
    estimate_row = persist_effect_estimate(session, participant_id, recommendation_id, result)

    weeks_active = weeks_active_for_type(session, participant_id, intervention_type, as_of_date)
    phase = phase_from_evidence(current_n_observations, weeks_active, config)

    from app.personalization.db_adapter import historical_compliance_values

    compliance_values = historical_compliance_values(session, participant_id, intervention_type, as_of_date)
    model_result = build_personal_effect_model(intervention_type, estimate_row, compliance_values, config)

    if existing is None:
        existing = PersonalEffectModel(participant_id=participant_id, intervention_type=intervention_type)
        session.add(existing)

    existing.slope = model_result.slope
    existing.intercept = model_result.intercept
    existing.r_squared = model_result.r_squared
    existing.num_observations = current_n_observations
    existing.personalization_phase = phase
    existing.confidence_interval_lower = model_result.confidence_interval_lower
    existing.confidence_interval_upper = model_result.confidence_interval_upper
    existing.model_version = config.personalization_config_version
    existing.evidence_source = model_result.evidence_source

    session.commit()
    return UpdateOutcome(UPDATED, intervention_type, existing)

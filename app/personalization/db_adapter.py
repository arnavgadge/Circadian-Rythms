"""Read-side adapter for the Phase 13 personalization system.

Everything here is a plain SQL read against existing tables
(``intervention_log``, ``recommendations``, ``intervention_effect_estimates``,
``personal_effect_models``, ``bandit_state``, ``participants``) -- no
parallel in-memory state. **Every query that could see "the future"
relative to a given ``as_of_date`` filters on it explicitly** (see
``docs/personalization_engine.md`` "Temporal leakage prevention") --
this is the one module responsible for that guarantee; every other
Phase 13 module only sees data this adapter already scoped correctly.
"""

from __future__ import annotations

from datetime import date as date_cls
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    BanditState,
    InterventionEffectEstimate,
    InterventionLog,
    Participant,
    PersonalEffectModel,
    Recommendation,
)


def count_compliance_observations(
    session: Session, participant_id: int, intervention_type: str, as_of_date: date_cls
) -> int:
    """Every day **strictly before** ``as_of_date`` this intervention
    type was logged with a resolved compliance value -- across all
    catalogue rows of that type and all episodes, matching Phase 12's
    own "evidence count" concept."""

    rows = session.execute(
        select(InterventionLog.id)
        .join(Recommendation, InterventionLog.recommendation_id == Recommendation.id)
        .where(
            InterventionLog.participant_id == participant_id,
            Recommendation.intervention_type == intervention_type,
            InterventionLog.log_date < as_of_date,
            InterventionLog.compliance_degree.is_not(None),
        )
    ).scalars().all()
    return len(rows)


def first_exposure_date(session: Session, participant_id: int, intervention_type: str, as_of_date: date_cls) -> Optional[date_cls]:
    row = session.execute(
        select(InterventionLog.log_date)
        .join(Recommendation, InterventionLog.recommendation_id == Recommendation.id)
        .where(
            InterventionLog.participant_id == participant_id,
            Recommendation.intervention_type == intervention_type,
            InterventionLog.log_date < as_of_date,
        )
        .order_by(InterventionLog.log_date.asc())
    ).scalars().first()
    return row


def weeks_active_for_type(session: Session, participant_id: int, intervention_type: str, as_of_date: date_cls) -> float:
    first_date = first_exposure_date(session, participant_id, intervention_type, as_of_date)
    if first_date is None:
        return 0.0
    return max(0.0, (as_of_date - first_date).days / 7.0)


def latest_effect_estimate(
    session: Session, participant_id: int, intervention_type: str, as_of_date: date_cls
) -> Optional[InterventionEffectEstimate]:
    """The most recent Phase 12 estimate for this intervention type,
    restricted to estimates **computed from data available before**
    ``as_of_date`` -- never an estimate whose own period could include
    ``as_of_date`` or later."""

    return session.execute(
        select(InterventionEffectEstimate)
        .join(Recommendation, InterventionEffectEstimate.recommendation_id == Recommendation.id)
        .where(
            InterventionEffectEstimate.participant_id == participant_id,
            Recommendation.intervention_type == intervention_type,
            (InterventionEffectEstimate.period_end.is_(None)) | (InterventionEffectEstimate.period_end < as_of_date),
        )
        .order_by(InterventionEffectEstimate.created_at.desc())
    ).scalars().first()


def latest_recommendation_id_for_type(
    session: Session, intervention_type: str
) -> Optional[int]:
    """The catalogue's current active recommendation for this type --
    used by the update pipeline to know which specific ``recommendation_id``
    to run Phase 12 evaluation against (today's catalogue has exactly
    one active row per type, but this does not assume that stays true)."""

    return session.execute(
        select(Recommendation.id).where(Recommendation.intervention_type == intervention_type, Recommendation.is_active.is_(True))
    ).scalars().first()


def load_personal_effect_model(session: Session, participant_id: int, intervention_type: str) -> Optional[PersonalEffectModel]:
    return session.execute(
        select(PersonalEffectModel).where(
            PersonalEffectModel.participant_id == participant_id, PersonalEffectModel.intervention_type == intervention_type
        )
    ).scalars().first()


def load_bandit_state(session: Session, participant_id: int, intervention_type: str) -> Optional[BanditState]:
    return session.execute(
        select(BanditState).where(BanditState.participant_id == participant_id, BanditState.intervention_type == intervention_type)
    ).scalars().first()


def historical_compliance_values(
    session: Session, participant_id: int, intervention_type: str, as_of_date: date_cls
) -> list:
    """Raw ``compliance_degree`` values (strictly before ``as_of_date``)
    -- used for both compliance-probability estimation and the personal
    effect model's compliance-variation validity check."""

    return list(
        session.execute(
            select(InterventionLog.compliance_degree)
            .join(Recommendation, InterventionLog.recommendation_id == Recommendation.id)
            .where(
                InterventionLog.participant_id == participant_id,
                Recommendation.intervention_type == intervention_type,
                InterventionLog.log_date < as_of_date,
                InterventionLog.compliance_degree.is_not(None),
            )
        ).scalars().all()
    )

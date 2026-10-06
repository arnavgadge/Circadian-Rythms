"""Read/write access to ``intervention_log`` / ``recommendations`` /
``intervention_effect_estimates``."""

from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import InterventionEffectEstimate, InterventionLog, Recommendation


class InterventionRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_log(self, intervention_log_id: int) -> Optional[InterventionLog]:
        return self.session.get(InterventionLog, intervention_log_id)

    def get_recommendation(self, recommendation_id: int) -> Optional[Recommendation]:
        return self.session.get(Recommendation, recommendation_id)

    def get_latest_log(self, participant_id: int) -> Optional[InterventionLog]:
        return self.session.execute(
            select(InterventionLog).where(InterventionLog.participant_id == participant_id).order_by(InterventionLog.log_date.desc())
        ).scalars().first()

    def get_history(
        self,
        participant_id: int,
        start_date: Optional[date_type],
        end_date: Optional[date_type],
        intervention_type: Optional[str],
        limit: int,
    ) -> list:
        stmt = select(InterventionLog).where(InterventionLog.participant_id == participant_id)
        if start_date is not None:
            stmt = stmt.where(InterventionLog.log_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(InterventionLog.log_date <= end_date)
        if intervention_type is not None:
            stmt = stmt.join(Recommendation, InterventionLog.recommendation_id == Recommendation.id).where(
                Recommendation.intervention_type == intervention_type
            )
        stmt = stmt.order_by(InterventionLog.log_date.desc()).limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def get_latest_effect_estimate(self, participant_id: int, recommendation_id: int) -> Optional[InterventionEffectEstimate]:
        return self.session.execute(
            select(InterventionEffectEstimate)
            .where(
                InterventionEffectEstimate.participant_id == participant_id,
                InterventionEffectEstimate.recommendation_id == recommendation_id,
            )
            .order_by(InterventionEffectEstimate.created_at.desc())
        ).scalars().first()

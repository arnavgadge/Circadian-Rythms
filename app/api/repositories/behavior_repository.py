"""Read/write access to ``daily_observations``."""

from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import DailyObservation


class BehaviorRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert(self, participant_id: int, observation_date: date_type, **fields) -> DailyObservation:
        """Creates or updates the one ``daily_observations`` row for this
        participant/date -- pure persistence, no derived fields
        computed here (sleep duration, tier classification, etc. all
        remain Phase 4's job when the feature engine later reads this
        row)."""

        existing = self.get_for_date(participant_id, observation_date)
        if existing is not None:
            for key, value in fields.items():
                if value is not None:
                    setattr(existing, key, value)
            self.session.flush()
            return existing

        row = DailyObservation(participant_id=participant_id, observation_date=observation_date, **fields)
        self.session.add(row)
        self.session.flush()
        return row

    def get_history(
        self, participant_id: int, start_date: Optional[date_type], end_date: Optional[date_type], limit: int
    ) -> list:
        stmt = select(DailyObservation).where(DailyObservation.participant_id == participant_id)
        if start_date is not None:
            stmt = stmt.where(DailyObservation.observation_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(DailyObservation.observation_date <= end_date)
        stmt = stmt.order_by(DailyObservation.observation_date.desc()).limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def get_for_date(self, participant_id: int, observation_date: date_type) -> Optional[DailyObservation]:
        return self.session.execute(
            select(DailyObservation).where(
                DailyObservation.participant_id == participant_id, DailyObservation.observation_date == observation_date
            )
        ).scalars().first()

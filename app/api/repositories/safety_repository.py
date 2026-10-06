"""Read access to ``safety_flags``."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import SafetyFlag


class SafetyRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_active_flags(self, participant_id: int) -> list:
        return list(
            self.session.execute(
                select(SafetyFlag).where(SafetyFlag.participant_id == participant_id, SafetyFlag.resolved_date.is_(None))
            ).scalars().all()
        )

"""Read/write access to ``participants`` / ``participant_profiles``.
Services depend on this, never on raw SQLAlchemy queries scattered
through routes."""

from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Participant, ParticipantProfile


class ParticipantRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, participant_id: int) -> Optional[Participant]:
        return self.session.get(Participant, participant_id)

    def get_profile(self, participant_id: int) -> Optional[ParticipantProfile]:
        return self.session.get(ParticipantProfile, participant_id)

    def get_by_code(self, participant_code: str) -> Optional[Participant]:
        return self.session.execute(
            select(Participant).where(Participant.participant_code == participant_code)
        ).scalars().first()

    def create(self, participant_code: str, enrollment_date: date_type) -> Participant:
        participant = Participant(participant_code=participant_code, enrollment_date=enrollment_date, status="active")
        self.session.add(participant)
        self.session.flush()
        return participant

    def create_profile(self, participant_id: int, **fields) -> ParticipantProfile:
        profile = ParticipantProfile(participant_id=participant_id, **fields)
        self.session.add(profile)
        self.session.flush()
        return profile

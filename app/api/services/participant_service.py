"""Application service for participant profile reads/onboarding."""

from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from app.api.errors import ConflictError, NotFoundError
from app.api.formatting import format_time
from app.api.repositories.participant_repository import ParticipantRepository
from app.api.schemas.onboarding import OnboardingRequest, OnboardingResponse
from app.api.schemas.participant import ParticipantResponse
from app.synthetic.time_utils import hour_to_clock_time


class ParticipantService:
    def __init__(self, repository: ParticipantRepository):
        self.repository = repository

    def get_participant(self, participant_id: int) -> ParticipantResponse:
        participant = self.repository.get(participant_id)
        if participant is None:
            raise NotFoundError("Participant not found", detail=f"participant_id={participant_id}")

        profile = self.repository.get_profile(participant_id)

        return ParticipantResponse(
            participant_id=participant.id,
            participant_code=participant.participant_code,
            chronotype=profile.chronotype_category if profile else None,
            estimated_biological_clock=format_time(profile.current_dlmo_time) if profile else None,
            adapted_biological_clock=format_time(profile.adapted_dlmo_time) if profile else None,
            current_alignment_score=profile.current_alignment_score if profile else None,
            status=participant.status,
            enrollment_date=participant.enrollment_date,
        )

    def onboard(self, request: OnboardingRequest) -> OnboardingResponse:
        existing = self.repository.get_by_code(request.participant_code)
        if existing is not None:
            raise ConflictError("A participant with this code already exists", detail=request.participant_code)

        enrollment_date = request.enrollment_date or date_type.today()
        participant = self.repository.create(request.participant_code, enrollment_date)

        # Deliberately does NOT compute/initialize intrinsic_dlmo_time
        # here -- no earlier phase implements a real MEQ/MCTQ -> DLMO
        # formula (only the Phase 3 synthetic generator fabricates one
        # for simulation purposes), and Phase 15 must not invent a new
        # biological algorithm. The questionnaire baseline is stored;
        # a prediction becomes available once enough behavioral history
        # exists for daily inference to run (see OnboardingResponse.note).
        msfsc_time_value = None
        if request.msfsc_time is not None:
            hour, minute = (int(p) for p in request.msfsc_time.split(":"))
            from datetime import time as time_cls

            msfsc_time_value = time_cls(hour=hour, minute=minute)

        self.repository.create_profile(
            participant.id,
            chronotype_category=request.chronotype,
            meq_score=request.meq_score,
            msfsc_time=msfsc_time_value,
        )
        self.repository.session.commit()

        return OnboardingResponse(participant_id=participant.id, participant_code=participant.participant_code, status=participant.status)

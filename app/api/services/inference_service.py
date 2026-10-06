"""Application service for the daily-inference endpoint.

Composes two already-complete phases -- Phase 11's
``run_daily_inference`` and Phase 14's ``SafetyEngine.evaluate`` -- in
sequence. **Never reimplements either.** This is the one place in the
API that triggers computation; every other service is read-only.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Optional

from sqlalchemy.orm import Session, sessionmaker

from app.api.errors import DependencyUnavailableError, NotFoundError, ValidationFailedError
from app.api.schemas.inference import InferenceResponse
from app.api.services.status_service import StatusService
from app.pipeline.orchestrator import run_daily_inference
from app.pipeline.types import FAILED
from app.safety.engine import RecommendationInput, SafetyEngine

# "traits" failing means the participant simply isn't ready for
# inference yet (e.g. no intrinsic biological clock established) --
# a client-correctable state, not an infrastructure problem.
_CLIENT_FAILURE_STAGES = {"traits"}


class InferenceService:
    def __init__(self, session_factory: sessionmaker, session: Session, status_service: StatusService, safety_engine: SafetyEngine):
        self.session_factory = session_factory
        self.session = session
        self.status_service = status_service
        self.safety_engine = safety_engine

    def run(self, participant_id: int, target_date: Optional[date_type], force_rerun: bool) -> InferenceResponse:
        target_date = target_date or date_type.today()

        result = run_daily_inference(participant_id, target_date, self.session_factory, force_rerun=force_rerun)

        if result.status == FAILED:
            if result.failure_stage == "read":
                # Only reached via a deliberately-authored ValueError
                # from app.pipeline.read (unknown participant, target-day
                # leakage guard, etc.) -- safe to forward verbatim.
                raise NotFoundError("Participant or inference input not found", detail=result.failure_message)
            if result.failure_stage == "read_infrastructure":
                # A raw DB-layer error was caught here; its message may
                # contain connection/query detail and must never reach
                # the client (same principle as every other stage below).
                raise DependencyUnavailableError("Daily inference could not complete", detail=f"stage={result.failure_stage}")
            if result.failure_stage in _CLIENT_FAILURE_STAGES:
                raise ValidationFailedError(
                    "This participant is not yet ready for inference", detail=f"stage={result.failure_stage}: {result.failure_message}"
                )
            # Unlike "read"/"traits" (controlled, client-safe ValueError
            # messages raised deliberately by the pipeline's own
            # validation), every other failure stage catches a bare
            # ``except Exception`` -- its message may be a raw
            # SQLAlchemy/database error and must never reach the client
            # (see docs/api_architecture.md #8: "no stack trace or
            # database detail is ever leaked"). Only the stage name,
            # never ``result.failure_message``, is client-safe here; the
            # full message is already logged server-side by the pipeline.
            raise DependencyUnavailableError("Daily inference could not complete", detail=f"stage={result.failure_stage}")

        if result.fusion_result is not None:
            recommendation_input = None
            if result.recommendation_result is not None and result.recommendation_result.primary is not None:
                primary = result.recommendation_result.primary
                recommendation_input = RecommendationInput(intervention_type=primary.intervention_type, text=primary.text)

            self.safety_engine.evaluate(
                self.session, participant_id, target_date, result.fusion_result, result.alignment_result, recommendation_input, persist=True
            )
            self.session.commit()

        status = self.status_service.build_status(participant_id, target_date)

        return InferenceResponse(
            participant_id=participant_id, target_date=target_date, pipeline_status=result.status,
            idempotent_short_circuit=result.idempotent_short_circuit, persistence_status=result.persistence_status, status=status,
        )

"""FastAPI dependency injection: database session, repositories,
services, configuration. No global mutable session -- a fresh
``Session`` is created per request (via ``get_db_session``) and closed
when the request ends.
"""

from __future__ import annotations

from typing import Iterator

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from app.api.config import APIConfig
from app.api.repositories.behavior_repository import BehaviorRepository
from app.api.repositories.circadian_repository import CircadianRepository
from app.api.repositories.intervention_repository import InterventionRepository
from app.api.repositories.participant_repository import ParticipantRepository
from app.api.repositories.safety_repository import SafetyRepository
from app.api.services.behavior_service import BehaviorService
from app.api.services.contributor_service import ContributorService
from app.api.services.health_service import HealthService
from app.api.services.history_service import HistoryService
from app.api.services.inference_service import InferenceService
from app.api.services.intervention_service import InterventionService
from app.api.services.participant_service import ParticipantService
from app.api.services.recommendation_service import RecommendationService
from app.api.services.safety_service import SafetyService
from app.api.services.status_service import StatusService
from app.safety.engine import SafetyEngine


def get_api_config(request: Request) -> APIConfig:
    return request.app.state.api_config


def get_session_factory(request: Request) -> sessionmaker:
    return request.app.state.session_factory


def get_db_session(session_factory: sessionmaker = Depends(get_session_factory)) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


# --- Repositories ---


def get_participant_repository(session: Session = Depends(get_db_session)) -> ParticipantRepository:
    return ParticipantRepository(session)


def get_circadian_repository(session: Session = Depends(get_db_session)) -> CircadianRepository:
    return CircadianRepository(session)


def get_behavior_repository(session: Session = Depends(get_db_session)) -> BehaviorRepository:
    return BehaviorRepository(session)


def get_intervention_repository(session: Session = Depends(get_db_session)) -> InterventionRepository:
    return InterventionRepository(session)


def get_safety_repository(session: Session = Depends(get_db_session)) -> SafetyRepository:
    return SafetyRepository(session)


# --- Services ---


def get_health_service(api_config: APIConfig = Depends(get_api_config), session: Session = Depends(get_db_session)) -> HealthService:
    return HealthService(api_config, session)


def get_participant_service(repository: ParticipantRepository = Depends(get_participant_repository)) -> ParticipantService:
    return ParticipantService(repository)


def get_status_service(
    participant_repository: ParticipantRepository = Depends(get_participant_repository),
    circadian_repository: CircadianRepository = Depends(get_circadian_repository),
    intervention_repository: InterventionRepository = Depends(get_intervention_repository),
    safety_repository: SafetyRepository = Depends(get_safety_repository),
) -> StatusService:
    return StatusService(participant_repository, circadian_repository, intervention_repository, safety_repository)


def get_safety_engine() -> SafetyEngine:
    return SafetyEngine()


def get_inference_service(
    session_factory: sessionmaker = Depends(get_session_factory),
    session: Session = Depends(get_db_session),
    status_service: StatusService = Depends(get_status_service),
    safety_engine: SafetyEngine = Depends(get_safety_engine),
) -> InferenceService:
    return InferenceService(session_factory, session, status_service, safety_engine)


def get_history_service(repository: CircadianRepository = Depends(get_circadian_repository)) -> HistoryService:
    return HistoryService(repository)


def get_behavior_service(
    repository: BehaviorRepository = Depends(get_behavior_repository), session: Session = Depends(get_db_session)
) -> BehaviorService:
    return BehaviorService(repository, session)


def get_contributor_service(repository: CircadianRepository = Depends(get_circadian_repository)) -> ContributorService:
    return ContributorService(repository)


def get_recommendation_service(
    circadian_repository: CircadianRepository = Depends(get_circadian_repository),
    intervention_repository: InterventionRepository = Depends(get_intervention_repository),
    safety_repository: SafetyRepository = Depends(get_safety_repository),
) -> RecommendationService:
    return RecommendationService(circadian_repository, intervention_repository, safety_repository)


def get_intervention_service(
    repository: InterventionRepository = Depends(get_intervention_repository), session: Session = Depends(get_db_session)
) -> InterventionService:
    return InterventionService(repository, session)


def get_safety_service(
    safety_repository: SafetyRepository = Depends(get_safety_repository), circadian_repository: CircadianRepository = Depends(get_circadian_repository)
) -> SafetyService:
    return SafetyService(safety_repository, circadian_repository)

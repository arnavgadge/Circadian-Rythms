"""Constraint-level tests: foreign keys, uniqueness, and invalid references."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.database.models import DailyObservation, Participant, Recommendation


def _make_participant(session, code: str = "P0001") -> Participant:
    participant = Participant(participant_code=code, enrollment_date=date(2026, 1, 1))
    session.add(participant)
    session.commit()
    return participant


def test_foreign_key_relationship_resolves(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session)
    observation = DailyObservation(
        participant_id=participant.id, observation_date=date(2026, 1, 1)
    )
    session.add(observation)
    session.commit()

    session.refresh(observation)
    assert observation.participant.id == participant.id
    session.close()


def test_invalid_foreign_key_reference_is_rejected(db_session_factory):
    session = db_session_factory()
    observation = DailyObservation(participant_id=999_999, observation_date=date(2026, 1, 1))
    session.add(observation)

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.close()


def test_participant_code_uniqueness_is_enforced(db_session_factory):
    session = db_session_factory()
    session.add(Participant(participant_code="DUP", enrollment_date=date(2026, 1, 1)))
    session.commit()

    session.add(Participant(participant_code="DUP", enrollment_date=date(2026, 1, 2)))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.close()


def test_daily_observation_participant_date_uniqueness_is_enforced(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session)
    session.add(
        DailyObservation(participant_id=participant.id, observation_date=date(2026, 1, 1))
    )
    session.commit()

    session.add(
        DailyObservation(participant_id=participant.id, observation_date=date(2026, 1, 1))
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.close()


def test_recommendation_intervention_code_uniqueness_is_enforced(db_session_factory):
    session = db_session_factory()
    session.add(Recommendation(intervention_code="DUP_CODE", intervention_type="light", title="A"))
    session.commit()

    session.add(Recommendation(intervention_code="DUP_CODE", intervention_type="light", title="B"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.close()

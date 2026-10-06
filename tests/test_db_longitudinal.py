"""Longitudinal, immutability, and relationship-behavior tests."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database.models import (
    CircadianLabel,
    InterventionLog,
    Participant,
    ParticipantProfile,
    Recommendation,
)


def _make_participant(session, code: str = "P0001") -> Participant:
    participant = Participant(participant_code=code, enrollment_date=date(2026, 1, 1))
    session.add(participant)
    session.commit()
    return participant


def test_longitudinal_records_can_be_inserted_across_many_dates(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session)

    for day in range(1, 6):
        session.add(
            CircadianLabel(
                participant_id=participant.id,
                target_date=date(2026, 1, day),
                prediction_status="success",
            )
        )
    session.commit()

    stored = (
        session.execute(
            select(CircadianLabel).where(CircadianLabel.participant_id == participant.id)
        )
        .scalars()
        .all()
    )
    assert len(stored) == 5
    session.close()


def test_historical_predictions_are_distinguishable_and_not_overwritten(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session)
    target_date = date(2026, 1, 10)

    first = CircadianLabel(
        participant_id=participant.id,
        target_date=target_date,
        prediction_status="success",
        confidence_score=0.4,
        is_latest=True,
    )
    session.add(first)
    session.commit()

    # A re-run supersedes the old prediction with a new immutable row
    # instead of overwriting it.
    first.is_latest = False
    second = CircadianLabel(
        participant_id=participant.id,
        target_date=target_date,
        prediction_status="success",
        confidence_score=0.9,
        is_latest=True,
    )
    session.add(second)
    session.commit()

    rows = (
        session.execute(
            select(CircadianLabel)
            .where(CircadianLabel.participant_id == participant.id)
            .where(CircadianLabel.target_date == target_date)
            .order_by(CircadianLabel.id)
        )
        .scalars()
        .all()
    )

    assert len(rows) == 2
    assert rows[0].confidence_score == 0.4 and rows[0].is_latest is False
    assert rows[1].confidence_score == 0.9 and rows[1].is_latest is True
    session.close()


def test_current_participant_state_can_be_updated_in_place(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session)

    profile = ParticipantProfile(
        participant_id=participant.id, chronotype_category="intermediate"
    )
    session.add(profile)
    session.commit()

    profile.current_alignment_score = 55.0
    profile.current_alignment_date = date(2026, 1, 1)
    session.commit()

    profile.current_alignment_score = 72.5
    profile.current_alignment_date = date(2026, 1, 2)
    session.commit()

    reloaded = session.get(ParticipantProfile, participant.id)
    assert reloaded.current_alignment_score == 72.5
    assert reloaded.chronotype_category == "intermediate"

    all_profiles = (
        session.execute(
            select(ParticipantProfile).where(
                ParticipantProfile.participant_id == participant.id
            )
        )
        .scalars()
        .all()
    )
    assert len(all_profiles) == 1
    session.close()


def test_intervention_log_references_recommendation_correctly(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session)
    recommendation = Recommendation(
        intervention_code="MORNING_LIGHT_EXPOSURE",
        intervention_type="light",
        title="Morning bright light exposure",
    )
    session.add(recommendation)
    session.commit()

    log_entry = InterventionLog(
        participant_id=participant.id,
        recommendation_id=recommendation.id,
        log_date=date(2026, 1, 1),
    )
    session.add(log_entry)
    session.commit()

    session.refresh(log_entry)
    assert log_entry.recommendation.intervention_code == "MORNING_LIGHT_EXPOSURE"
    session.close()


def test_recommendation_cannot_be_deleted_while_referenced(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session)
    recommendation = Recommendation(
        intervention_code="EVENING_SCREEN_REDUCTION",
        intervention_type="screen",
        title="Reduce screens",
    )
    session.add(recommendation)
    session.commit()

    session.add(
        InterventionLog(
            participant_id=participant.id,
            recommendation_id=recommendation.id,
            log_date=date(2026, 1, 1),
        )
    )
    session.commit()

    session.delete(recommendation)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.close()


def test_deleting_a_participant_cascades_to_owned_data(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session)
    session.add(
        CircadianLabel(
            participant_id=participant.id, target_date=date(2026, 1, 1), prediction_status="success"
        )
    )
    session.add(
        ParticipantProfile(participant_id=participant.id, chronotype_category="intermediate")
    )
    session.commit()

    session.delete(participant)
    session.commit()

    remaining_labels = (
        session.execute(
            select(CircadianLabel).where(CircadianLabel.participant_id == participant.id)
        )
        .scalars()
        .all()
    )
    remaining_profiles = (
        session.execute(
            select(ParticipantProfile).where(
                ParticipantProfile.participant_id == participant.id
            )
        )
        .scalars()
        .all()
    )

    assert remaining_labels == []
    assert remaining_profiles == []
    session.close()

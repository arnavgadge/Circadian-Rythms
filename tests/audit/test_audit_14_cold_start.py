"""AUDIT 14 -- Cold start and independent per-intervention-type phase
progression.

Uses ``app.personalization.dispatcher.get_personalization_phase``
against a real (SQLite) database, building up compliance history
incrementally for one intervention type only, to verify:

1. A brand-new participant with zero history starts at LITERATURE.
2. Progression through PERSONAL_RANKING -> PERSONAL_EFFECT ->
   ADAPTIVE_POLICY happens at the documented threshold constants in
   ``app.personalization.config.PersonalizationConfig``.
3. Each intervention type's phase is tracked independently -- a
   participant can be far along for one intervention type while a
   second, never-recommended type stays at LITERATURE.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.database.models import InterventionLog, Participant, ParticipantProfile, Recommendation
from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG
from app.personalization.dispatcher import get_personalization_phase
from app.recommendations.personalization import ADAPTIVE_POLICY, LITERATURE, PERSONAL_EFFECT, PERSONAL_RANKING
from app.synthetic.time_utils import hour_to_clock_time

BASE_DATE = date(2026, 1, 1)
CONFIG = DEFAULT_PERSONALIZATION_CONFIG


@pytest.fixture
def cold_start_session(db_session_factory):
    session = db_session_factory()
    participant = Participant(participant_code="COLD-001", enrollment_date=BASE_DATE, status="active")
    session.add(participant)
    session.flush()
    session.add(
        ParticipantProfile(
            participant_id=participant.id, chronotype_category="Intermediate",
            intrinsic_dlmo_time=hour_to_clock_time(21.0), adapted_dlmo_time=hour_to_clock_time(21.0),
            current_dlmo_time=hour_to_clock_time(21.0),
        )
    )
    screen_rec = Recommendation(
        intervention_code="COLD_SCREEN", intervention_type="screen", title="screen",
        target_behavior="evening_screen_duration", literature_expected_improvement_minutes=15.0,
        source="test fixture", extra_metadata={"contributor_signals": ["evening_screen"], "value_kind": "clock_hour", "direction": "earlier"},
    )
    meal_rec = Recommendation(
        intervention_code="COLD_MEAL", intervention_type="meal", title="meal",
        target_behavior="last_meal_time", literature_expected_improvement_minutes=8.0,
        source="test fixture", extra_metadata={"contributor_signals": ["meal_timing"], "value_kind": "clock_hour", "direction": "earlier"},
    )
    session.add_all([screen_rec, meal_rec])
    session.flush()
    session.commit()
    yield session, participant.id, screen_rec.id, meal_rec.id
    session.close()


def _log_daily_compliance(session, participant_id, recommendation_id, start_date, n_days, compliance=0.9):
    for i in range(n_days):
        session.add(
            InterventionLog(
                participant_id=participant_id, recommendation_id=recommendation_id,
                log_date=start_date + timedelta(days=i),
                recommendation_text="test", target_value_time=hour_to_clock_time(21.5),
                compliance_degree=compliance, compliance_binary=compliance >= 0.65,
                expected_improvement_minutes=15.0, personalization_phase="literature",
            )
        )
    session.commit()


def test_brand_new_participant_starts_at_literature(cold_start_session):
    session, participant_id, screen_rec_id, meal_rec_id = cold_start_session
    as_of = BASE_DATE
    assert get_personalization_phase(session, participant_id, "screen", as_of) == LITERATURE
    assert get_personalization_phase(session, participant_id, "meal", as_of) == LITERATURE


@pytest.mark.parametrize(
    "n_days_before_asof,expected_phase",
    [
        (2, LITERATURE),  # below ranking_min_observations (3)
        (CONFIG.ranking_min_observations, LITERATURE),  # obs met but weeks_active not yet (same-day logging)
    ],
)
def test_progression_requires_both_observation_and_weeks_gates(cold_start_session, n_days_before_asof, expected_phase):
    session, participant_id, screen_rec_id, meal_rec_id = cold_start_session
    start = BASE_DATE
    as_of = start  # weeks_active == 0 regardless of observation count logged "at once"
    _log_daily_compliance(session, participant_id, screen_rec_id, start - timedelta(days=n_days_before_asof), n_days_before_asof)
    phase = get_personalization_phase(session, participant_id, "screen", as_of)
    assert phase == LITERATURE  # as_of == start of history -> weeks_active == 0 always blocks graduation


def test_progression_through_documented_thresholds(cold_start_session):
    session, participant_id, screen_rec_id, meal_rec_id = cold_start_session
    start = BASE_DATE

    # Enough observations AND weeks active for PERSONAL_RANKING, but not PERSONAL_EFFECT.
    ranking_weeks_days = CONFIG.ranking_min_weeks_active * 7
    _log_daily_compliance(session, participant_id, screen_rec_id, start, ranking_weeks_days)
    as_of = start + timedelta(days=ranking_weeks_days)
    phase = get_personalization_phase(session, participant_id, "screen", as_of)
    assert phase == PERSONAL_RANKING, (
        f"expected PERSONAL_RANKING at {CONFIG.ranking_min_observations} obs / "
        f"{CONFIG.ranking_min_weeks_active} weeks, got {phase}"
    )

    # meal_timing has never been recommended -- must remain LITERATURE independently.
    assert get_personalization_phase(session, participant_id, "meal", as_of) == LITERATURE

    # Extend to PERSONAL_EFFECT thresholds.
    effect_weeks_days = CONFIG.effect_model_min_weeks_active * 7
    _log_daily_compliance(
        session, participant_id, screen_rec_id, start + timedelta(days=ranking_weeks_days), effect_weeks_days - ranking_weeks_days
    )
    as_of = start + timedelta(days=effect_weeks_days)
    phase = get_personalization_phase(session, participant_id, "screen", as_of)
    assert phase == PERSONAL_EFFECT, (
        f"expected PERSONAL_EFFECT at {CONFIG.effect_model_min_observations} obs / "
        f"{CONFIG.effect_model_min_weeks_active} weeks, got {phase}"
    )
    assert get_personalization_phase(session, participant_id, "meal", as_of) == LITERATURE

    # Extend to ADAPTIVE_POLICY thresholds.
    adaptive_weeks_days = CONFIG.adaptive_min_weeks_active * 7
    _log_daily_compliance(
        session, participant_id, screen_rec_id, start + timedelta(days=effect_weeks_days), adaptive_weeks_days - effect_weeks_days
    )
    as_of = start + timedelta(days=adaptive_weeks_days)
    phase = get_personalization_phase(session, participant_id, "screen", as_of)
    assert phase == ADAPTIVE_POLICY, (
        f"expected ADAPTIVE_POLICY at {CONFIG.adaptive_min_observations} obs / "
        f"{CONFIG.adaptive_min_weeks_active} weeks, got {phase}"
    )

    # meal_timing STILL independently at LITERATURE despite screen being fully adaptive.
    assert get_personalization_phase(session, participant_id, "meal", as_of) == LITERATURE


def test_independent_progression_when_both_types_have_history_at_different_rates(cold_start_session):
    """screen gets heavy daily history; meal gets only sparse history --
    verify each type's phase reflects only its OWN evidence."""

    session, participant_id, screen_rec_id, meal_rec_id = cold_start_session
    start = BASE_DATE

    heavy_days = CONFIG.effect_model_min_weeks_active * 7
    _log_daily_compliance(session, participant_id, screen_rec_id, start, heavy_days)

    # Sparse meal history: only ranking_min_observations logged, spread far enough
    # apart in time to clear the weeks-active gate but clearly below effect-model volume.
    for i in range(CONFIG.ranking_min_observations):
        session.add(
            InterventionLog(
                participant_id=participant_id, recommendation_id=meal_rec_id,
                log_date=start + timedelta(days=i * 7),
                recommendation_text="test", target_value_time=hour_to_clock_time(20.0),
                compliance_degree=0.8, compliance_binary=True,
                expected_improvement_minutes=8.0, personalization_phase="literature",
            )
        )
    session.commit()

    as_of = start + timedelta(days=heavy_days)
    screen_phase = get_personalization_phase(session, participant_id, "screen", as_of)
    meal_phase = get_personalization_phase(session, participant_id, "meal", as_of)

    assert screen_phase == PERSONAL_EFFECT
    assert meal_phase == PERSONAL_RANKING
    assert screen_phase != meal_phase

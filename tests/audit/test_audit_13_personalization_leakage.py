"""AUDIT 13 (HIGH PRIORITY) -- Personalization temporal-leakage replay test.

Builds a multi-day synthetic intervention history for one participant
(reusing the same hand-built ground-truth harness pattern as
``tests/test_effectiveness_db.py``), then asks: does
``app.personalization.update.update_personalization_state`` -- called
with an explicit ``as_of_date`` in the middle of that history -- ever
produce a different result depending on whether rows dated >= as_of_date
exist in the database?

If it does, the persisted ``personal_effect_models`` row (which later
feeds ``app.personalization.dispatcher.personalize_recommendations``)
would encode information about the future relative to the day it
claims to represent -- a real leakage bug, not a theoretical one.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.database.engine import create_app_engine, create_session_factory
from app.database.init_db import create_all_tables
from app.database.models import (
    AlignmentResult,
    CircadianLabel,
    DailyObservation,
    InterventionLog,
    Participant,
    ParticipantProfile,
    Recommendation,
)
from app.personalization.update import update_personalization_state
from app.synthetic.time_utils import hour_to_clock_time, normalize_hour
from tests.conftest import build_test_config

BASE_DATE = date(2026, 3, 1)
TRUE_EFFECT_MINUTES = -12.0


def _build_participant(session, code: str, n_days: int):
    """Same construction as tests/test_effectiveness_db.py's
    harness_session, parameterized on how many days of history exist in
    the DB -- lets us build a "short" DB (data ends at day t) and a
    "long" DB (data continues well past day t) and compare."""

    participant = Participant(participant_code=code, enrollment_date=BASE_DATE, status="active")
    session.add(participant)
    session.flush()

    session.add(
        ParticipantProfile(
            participant_id=participant.id,
            chronotype_category="Intermediate",
            intrinsic_dlmo_time=hour_to_clock_time(21.0),
            adapted_dlmo_time=hour_to_clock_time(21.0),
            current_dlmo_time=hour_to_clock_time(21.0),
        )
    )

    recommendation = Recommendation(
        intervention_code=f"TEST_SCREEN_{code}",
        intervention_type="screen",
        title="Reduce evening screen exposure",
        target_behavior="evening_screen_duration",
        literature_expected_improvement_minutes=15.0,
        source="test fixture",
        extra_metadata={
            "contributor_signals": ["evening_screen"], "value_kind": "clock_hour", "direction": "earlier",
            "template": "Try stopping screens by {target_time}.",
            "desired_value_assumption": -0.5, "desired_value_relative_to": "ideal_sleep_onset",
            "max_shift_per_recommendation": 1.5, "baseline_feasibility": 0.5, "is_literature_verified": False,
        },
    )
    session.add(recommendation)
    session.flush()

    dlmo = 21.0
    for i in range(n_days):
        d = BASE_DATE + timedelta(days=i)
        is_intervention_day = i >= 7

        if is_intervention_day:
            compliance = ((i - 7) % 10) / 10.0
            dlmo = normalize_hour(dlmo + (TRUE_EFFECT_MINUTES * compliance) / 60.0)

        session.add(
            DailyObservation(
                participant_id=participant.id,
                observation_date=d,
                sleep_onset_time=hour_to_clock_time(dlmo + 2.0),
                morning_light_duration_minutes=50.0 + 5 * math.sin(i),
                evening_screen_duration_minutes=(0.5 * 60.0) if is_intervention_day else (3.0 * 60.0),
                last_meal_time=hour_to_clock_time(22.0 + 0.1 * math.cos(i)),
                exercise_time=hour_to_clock_time(18.0 + 0.1 * math.sin(i * 0.5)),
                last_caffeine_time=hour_to_clock_time(10.0),
                caffeine_amount_mg=0.0,
            )
        )
        session.flush()

        label = CircadianLabel(
            participant_id=participant.id, target_date=d, is_latest=True, prediction_status="success",
            fused_dlmo_time=hour_to_clock_time(dlmo), data_completeness=1.0,
        )
        session.add(label)
        session.flush()
        session.add(
            AlignmentResult(
                circadian_label_id=label.id, participant_id=participant.id, target_date=d,
                final_alignment_score=60.0 + i * 0.5, phase_alignment_score=60.0, behavioral_alignment_score=60.0,
            )
        )

        if is_intervention_day:
            compliance = ((i - 7) % 10) / 10.0
            session.add(
                InterventionLog(
                    participant_id=participant.id, recommendation_id=recommendation.id, log_date=d,
                    recommendation_text="Try stopping screens by 9:30 PM.",
                    target_value_time=hour_to_clock_time(21.5),
                    compliance_degree=compliance, compliance_binary=compliance >= 0.65,
                    expected_improvement_minutes=15.0, personalization_phase="literature",
                )
            )

    session.commit()
    return participant.id, recommendation.id


AS_OF_DAY_INDEX = 20  # ask "what would you have decided on day 20" (13 intervention days observed so far)


def _isolated_session_factory(tmp_path, name: str):
    """A fully independent SQLite database (own engine, own file) so two
    scenarios can be compared without one leaking rows into the other
    via a shared connection/session-factory."""

    db_dir = tmp_path / name
    db_dir.mkdir(parents=True, exist_ok=True)
    config = build_test_config(db_dir, db_filename=f"{name}.db")
    engine = create_app_engine(config)
    create_all_tables(engine)
    return create_session_factory(engine)


def test_update_personalization_state_ignores_data_dated_on_or_after_as_of_date(tmp_path):
    """THE key replay proof for audit 13/15: feed the system data
    through day 34 in the DB, ask it to build personalization state
    "as of" day 20, and confirm the resulting personal-effect model is
    IDENTICAL to what it would compute if the database only contained
    data through day 19 (nothing from day 20 onward)."""

    as_of_date = BASE_DATE + timedelta(days=AS_OF_DAY_INDEX)

    # DB "short": history ends the day before as_of_date -- no future rows exist at all.
    short_factory = _isolated_session_factory(tmp_path, "short")
    short_session = short_factory()
    short_participant_id, short_recommendation_id = _build_participant(short_session, "SHORT", AS_OF_DAY_INDEX)
    short_outcome = update_personalization_state(short_session, short_participant_id, "screen", as_of_date)

    # DB "long": the identical history up to as_of_date, PLUS 14 more days of
    # (higher-compliance, so distinguishable) future data the system must not see.
    # A fully independent database from "short" -- only its own future rows
    # differ.
    long_factory = _isolated_session_factory(tmp_path, "long")
    long_session = long_factory()
    long_participant_id, long_recommendation_id = _build_participant(long_session, "LONG", 35)
    long_outcome = update_personalization_state(long_session, long_participant_id, "screen", as_of_date)

    assert short_outcome.status == "updated", short_outcome.status
    assert long_outcome.status == "updated", long_outcome.status

    short_model = short_outcome.personal_effect_model
    long_model = long_outcome.personal_effect_model

    assert short_model.num_observations == long_model.num_observations, (
        "personalization state computed 'as of' the same date differs in observation count "
        "depending on whether future rows exist in the DB -- temporal leakage"
    )
    assert short_model.slope == pytest.approx(long_model.slope, abs=1e-9), (
        f"personal-effect slope leaks future data: short-DB={short_model.slope} "
        f"long-DB={long_model.slope} (both claim to represent as_of_date={as_of_date})"
    )
    assert short_model.personalization_phase == long_model.personalization_phase

    short_session.close()
    long_session.close()

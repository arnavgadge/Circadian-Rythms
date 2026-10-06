"""Database-integration tests for Phase 12: a controlled simulation
harness (since Phase 3 does not automatically generate intervention
history) that injects a known intervention/compliance scenario
directly, then verifies the effectiveness system can reconstruct
everything from SQL alone.
"""

from __future__ import annotations

import math
from datetime import date, time, timedelta

import pytest

from app.database.models import (
    AlignmentResult,
    CircadianLabel,
    DailyObservation,
    InterventionEffectEstimate,
    InterventionLog,
    Participant,
    ParticipantProfile,
    Recommendation,
)
from app.effectiveness.db_adapter import load_episodes, load_intervention_records, load_target_signal
from app.effectiveness.dispatcher import evaluate_intervention_effect
from app.effectiveness.persistence import persist_effect_estimate
from app.effectiveness.sanity import run_sanity_checks
from app.synthetic.time_utils import hour_to_clock_time, normalize_hour

BASE_DATE = date(2026, 3, 1)
TRUE_EFFECT_MINUTES = -12.0  # known synthetic ground truth: -12 min per full compliance unit


@pytest.fixture
def harness_session(db_session_factory):
    """Injects one participant with a hand-built 35-day history: a
    stable pre-intervention baseline, then an evening-screen
    intervention with a known, noise-free compliance -> DLMO-change
    relationship -- the "known synthetic ground truth" this test
    checks recovery against.
    """

    session = db_session_factory()

    participant = Participant(participant_code="EFFECT-001", enrollment_date=BASE_DATE, status="active")
    session.add(participant)
    session.flush()

    profile = ParticipantProfile(
        participant_id=participant.id,
        chronotype_category="Intermediate",
        intrinsic_dlmo_time=hour_to_clock_time(21.0),
        adapted_dlmo_time=hour_to_clock_time(21.0),
        current_dlmo_time=hour_to_clock_time(21.0),
    )
    session.add(profile)

    recommendation = Recommendation(
        intervention_code="TEST_EVENING_SCREEN_REDUCTION",
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
    for i in range(35):
        d = BASE_DATE + timedelta(days=i)
        is_intervention_day = i >= 7

        if is_intervention_day:
            compliance = ((i - 7) % 10) / 10.0
            dlmo = normalize_hour(dlmo + (TRUE_EFFECT_MINUTES * compliance) / 60.0)
        # Baseline days: DLMO held flat.

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
    yield session, participant.id, recommendation.id
    session.close()


def test_database_reconstruction_matches_injected_scenario(harness_session):
    session, participant_id, recommendation_id = harness_session

    episodes = load_episodes(session, participant_id, recommendation_id)
    assert len(episodes) == 1
    assert episodes[0].start_date == BASE_DATE + timedelta(days=7)
    assert len(episodes[0].log_dates) == 28

    records = load_intervention_records(session, participant_id, recommendation_id)
    assert len(records) == 28 + 7  # intervention days + the reconstructed baseline window
    assert all(records[d].dlmo_hour is not None for d in episodes[0].log_dates)


def test_known_synthetic_ground_truth_recovery_via_full_stack(harness_session):
    session, participant_id, recommendation_id = harness_session

    target_signal = load_target_signal(session, recommendation_id)
    assert target_signal == "evening_screen"

    episodes = load_episodes(session, participant_id, recommendation_id)
    episode = episodes[-1]
    records = load_intervention_records(session, participant_id, recommendation_id)

    result = evaluate_intervention_effect(recommendation_id, participant_id, target_signal, episode, records)

    assert result.chosen_phase == 3
    # Recovering the KNOWN synthetic ground truth (-12 min/compliance
    # unit) -- this is the injected fact, not a claim about real
    # human physiology (see docs "Synthetic truth vs. estimated effect").
    assert result.phase3.effect_mins_per_compliance_unit == pytest.approx(TRUE_EFFECT_MINUTES, abs=1.0)

    report = run_sanity_checks(result)
    assert report.ok, report.summary_lines()


# --- 24. Historical effect-estimate persistence ---


def test_effect_estimate_persistence_never_overwrites_history(harness_session):
    session, participant_id, recommendation_id = harness_session

    target_signal = load_target_signal(session, recommendation_id)
    episode = load_episodes(session, participant_id, recommendation_id)[-1]
    records = load_intervention_records(session, participant_id, recommendation_id)
    result = evaluate_intervention_effect(recommendation_id, participant_id, target_signal, episode, records)

    first_row = persist_effect_estimate(session, participant_id, recommendation_id, result)
    second_row = persist_effect_estimate(session, participant_id, recommendation_id, result)
    session.commit()

    assert first_row.id != second_row.id

    from sqlalchemy import select

    all_rows = session.execute(
        select(InterventionEffectEstimate).where(InterventionEffectEstimate.recommendation_id == recommendation_id)
    ).scalars().all()
    assert len(all_rows) == 2  # both retained -- the second never overwrote the first
    assert all(row.measurement_phase == 3 for row in all_rows)

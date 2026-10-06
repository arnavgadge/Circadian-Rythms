"""End-to-end API integration flows for Phase 15."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.database.models import CircadianLabel, InterventionLog, Participant, ParticipantProfile, Recommendation, SafetyFlag
from app.synthetic.time_utils import hour_to_clock_time

BASE_DATE = date(2026, 7, 1)


def _seed_full_participant(client, code: str, n_days: int = 7) -> int:
    session_factory = client.app.state.session_factory
    session = session_factory()
    participant = Participant(participant_code=code, enrollment_date=BASE_DATE, status="active")
    session.add(participant)
    session.flush()
    session.add(
        ParticipantProfile(
            participant_id=participant.id, chronotype_category="Intermediate",
            intrinsic_dlmo_time=hour_to_clock_time(21.0), adapted_dlmo_time=hour_to_clock_time(21.0),
            current_dlmo_time=hour_to_clock_time(21.0), meq_score=50.0,
            synthetic_personality_profile={"light_sensitivity": 1.0, "screen_sensitivity": 1.0, "meal_sensitivity": 1.0},
        )
    )
    from app.database.models import DailyObservation

    for i in range(n_days):
        d = BASE_DATE + timedelta(days=i)
        session.add(
            DailyObservation(
                participant_id=participant.id, observation_date=d, sleep_onset_time=hour_to_clock_time(23.0),
                sleep_offset_time=hour_to_clock_time(7.0), sleep_duration_minutes=480.0,
                morning_light_start_time=hour_to_clock_time(7.5), morning_light_duration_minutes=30.0,
                evening_screen_end_time=hour_to_clock_time(22.5), evening_screen_duration_minutes=90.0,
                last_meal_time=hour_to_clock_time(19.5), exercise_time=hour_to_clock_time(18.0),
                last_caffeine_time=hour_to_clock_time(9.0), caffeine_amount_mg=80.0,
                is_free_day=False, free_day_ratio=0.0,
                sleep_midpoint_time=hour_to_clock_time(3.0), sleep_midpoint_variability_minutes=10.0,
                msfsc_time=hour_to_clock_time(3.5),
            )
        )
    session.commit()
    pid = participant.id
    session.close()
    return pid


def _seed_catalogue(client) -> None:
    session = client.app.state.session_factory()
    from app.database.seed import seed_reference_data

    seed_reference_data(session)
    session.close()


# --- FLOW 1: onboard -> insert observations -> run inference -> GET status -> verify ---


def test_flow_1_onboard_through_status(api_client):
    onboard_response = api_client.post("/api/v1/participants", json={"participant_code": "FLOW-001", "meq_score": 50})
    assert onboard_response.status_code == 201
    pid = onboard_response.json()["participant_id"]

    # The onboarding endpoint deliberately does not establish an
    # intrinsic biological clock (see ParticipantService); this flow
    # simulates the data becoming available afterward (e.g. through a
    # future dedicated initialization process) by setting it directly,
    # then logs a week of behavioral observations through the same
    # database the API reads/writes.
    session = api_client.app.state.session_factory()
    from app.database.models import DailyObservation

    profile = session.get(ParticipantProfile, pid)
    profile.intrinsic_dlmo_time = hour_to_clock_time(21.0)
    profile.adapted_dlmo_time = hour_to_clock_time(21.0)
    profile.current_dlmo_time = hour_to_clock_time(21.0)
    for i in range(7):
        d = BASE_DATE + timedelta(days=i)
        session.add(
            DailyObservation(
                participant_id=pid, observation_date=d, sleep_onset_time=hour_to_clock_time(23.0),
                sleep_offset_time=hour_to_clock_time(7.0), sleep_duration_minutes=480.0,
                morning_light_start_time=hour_to_clock_time(7.5), morning_light_duration_minutes=30.0,
                evening_screen_end_time=hour_to_clock_time(22.5), evening_screen_duration_minutes=90.0,
                last_meal_time=hour_to_clock_time(19.5), exercise_time=hour_to_clock_time(18.0),
                last_caffeine_time=hour_to_clock_time(9.0), caffeine_amount_mg=80.0,
                is_free_day=False, free_day_ratio=0.0, sleep_midpoint_time=hour_to_clock_time(3.0),
                sleep_midpoint_variability_minutes=10.0, msfsc_time=hour_to_clock_time(3.5),
            )
        )
    session.commit()
    session.close()

    target_date = str(BASE_DATE + timedelta(days=7))
    inference_response = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": target_date})
    assert inference_response.status_code == 200
    assert inference_response.json()["pipeline_status"] == "SUCCESS"

    status_response = api_client.get(f"/api/v1/participants/{pid}/status")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["prediction_available"] is True
    assert body["biological_clock"] is not None
    assert body["target_date"] == target_date


# --- FLOW 2: run same inference twice -> verify idempotent behavior ---


def test_flow_2_idempotent_inference(api_client):
    pid = _seed_full_participant(api_client, "FLOW-002")
    target_date = str(BASE_DATE + timedelta(days=7))

    first = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": target_date})
    second = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": target_date})

    assert first.json()["idempotent_short_circuit"] is False
    assert second.json()["idempotent_short_circuit"] is True
    assert first.json()["status"]["biological_clock"] == second.json()["status"]["biological_clock"]

    session = api_client.app.state.session_factory()
    labels = session.query(CircadianLabel).filter(
        CircadianLabel.participant_id == pid, CircadianLabel.target_date == date.fromisoformat(target_date)
    ).all()
    session.close()
    assert len(labels) == 1


# --- FLOW 3: high-severity safety condition -> GET recommendation -> suppressed ---


def test_flow_3_high_severity_suppresses_recommendation(api_client):
    _seed_catalogue(api_client)
    pid = _seed_full_participant(api_client, "FLOW-003")
    target_date = BASE_DATE + timedelta(days=7)

    inference_response = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": str(target_date)})
    assert inference_response.status_code == 200

    # Simulate an already-established HIGH-severity safety condition
    # (Phase 14's own detectors are exercised in tests/test_safety*.py;
    # here we verify the API's suppression *contract*, not re-derive
    # the detection logic).
    session = api_client.app.state.session_factory()
    label = session.query(CircadianLabel).filter(CircadianLabel.participant_id == pid, CircadianLabel.is_latest.is_(True)).one()
    label.safety_severity = "HIGH"
    label.recommendation_suppressed = True
    session.add(
        SafetyFlag(
            participant_id=pid, flagged_date=target_date, flag_type="continuous_dlmo_drift", severity="HIGH",
            message_shown="Your estimated biological clock appears to be drifting consistently.", recommendation_suppressed=True,
        )
    )
    session.commit()
    session.close()

    recommendation_response = api_client.get(f"/api/v1/participants/{pid}/recommendation/current")
    assert recommendation_response.status_code == 200
    body = recommendation_response.json()
    assert body["available"] is False
    assert body["suppressed"] is True
    assert body["primary"] is None
    assert "healthcare professional" in body["safety_message"]

    safety_response = api_client.get(f"/api/v1/participants/{pid}/safety")
    assert safety_response.json()["highest_severity"] == "HIGH"
    assert safety_response.json()["recommendation_suppressed"] is True


# --- FLOW 4: record intervention outcome -> retrieve history -> verify persisted ---


def test_flow_4_record_outcome_and_retrieve_history(api_client):
    _seed_catalogue(api_client)
    pid = _seed_full_participant(api_client, "FLOW-004")

    session = api_client.app.state.session_factory()
    recommendation = session.query(Recommendation).filter(Recommendation.intervention_type == "screen").first()
    log = InterventionLog(
        participant_id=pid, recommendation_id=recommendation.id, log_date=BASE_DATE,
        target_value_time=hour_to_clock_time(21.5), recommendation_text="Try stopping screens by 9:30 PM.",
    )
    session.add(log)
    session.commit()
    log_id = log.id
    session.close()

    outcome_response = api_client.post(
        f"/api/v1/participants/{pid}/interventions/{log_id}/outcome",
        json={"observation_date": str(BASE_DATE), "actual_value_time": "21:40"},
    )
    assert outcome_response.status_code == 200
    assert outcome_response.json()["applied"] is True

    history_response = api_client.get(f"/api/v1/participants/{pid}/interventions")
    assert history_response.status_code == 200
    entries = history_response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["intervention_log_id"] == log_id
    assert entries[0]["compliance_degree"] == pytest.approx(outcome_response.json()["compliance_degree"])
    assert entries[0]["observation_status"] == "observed"

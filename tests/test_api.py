"""Tests for the Phase 15 application/API layer."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.database.models import (
    AlignmentResult,
    CircadianLabel,
    DailyObservation,
    InterventionLog,
    Participant,
    ParticipantProfile,
    Recommendation,
    SafetyFlag,
)
from app.synthetic.time_utils import hour_to_clock_time

BASE_DATE = date(2026, 6, 1)


def _seed_ready_participant(client, code: str, n_days: int = 7) -> int:
    """Directly injects a participant with an intrinsic biological
    clock and ``n_days`` of complete behavioral history -- the
    onboarding endpoint deliberately does not set an intrinsic value
    (see ParticipantService), so integration tests that need a
    genuinely inference-ready participant seed one directly, the same
    way earlier phases' fixtures do."""

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


def _seed_recommendation_catalogue(client) -> None:
    session_factory = client.app.state.session_factory
    session = session_factory()
    from app.database.seed import seed_reference_data

    seed_reference_data(session)
    session.close()


# --- 1. Health endpoint ---


def test_health_endpoint(api_client):
    response = api_client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["application_available"] is True
    assert body["database_connected"] is True
    assert isinstance(body["model_artifacts_available"], bool)
    assert "models" not in str(response.content)  # never a raw path leaked


# --- 11. Onboarding ---


def test_onboarding_creates_participant(api_client):
    response = api_client.post("/api/v1/participants", json={"participant_code": "API-001", "meq_score": 55, "chronotype": "Intermediate"})
    assert response.status_code == 201
    body = response.json()
    assert body["participant_code"] == "API-001"
    assert "note" in body


def test_onboarding_duplicate_code_is_conflict(api_client):
    api_client.post("/api/v1/participants", json={"participant_code": "API-DUP"})
    response = api_client.post("/api/v1/participants", json={"participant_code": "API-DUP"})
    assert response.status_code == 409


# --- 12. Request validation / 14, 15, 16 ---


def test_onboarding_rejects_out_of_range_meq(api_client):
    response = api_client.post("/api/v1/participants", json={"participant_code": "API-002", "meq_score": 500})
    assert response.status_code == 422


def test_onboarding_rejects_malformed_time(api_client):
    response = api_client.post("/api/v1/participants", json={"participant_code": "API-003", "msfsc_time": "not-a-time"})
    assert response.status_code == 422


def test_onboarding_rejects_missing_required_field(api_client):
    response = api_client.post("/api/v1/participants", json={})
    assert response.status_code == 422


def test_history_rejects_malformed_date(api_client):
    pid = _seed_ready_participant(api_client, "API-004")
    response = api_client.get(f"/api/v1/participants/{pid}/circadian/history?start_date=not-a-date")
    assert response.status_code == 422


# --- 2. Participant retrieval / 13. invalid participant ---


def test_get_participant(api_client):
    pid = _seed_ready_participant(api_client, "API-005")
    response = api_client.get(f"/api/v1/participants/{pid}")
    assert response.status_code == 200
    body = response.json()
    assert body["participant_id"] == pid
    assert body["boundary_note"] == "Estimated from behavioral patterns. Not a clinical measurement."


def test_get_invalid_participant_returns_404(api_client):
    response = api_client.get("/api/v1/participants/999999")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "notfound"
    assert "correlation_id" in body


# --- 3. Current status / 19. GET status does not trigger inference ---


def test_get_status_without_any_result_is_graceful(api_client):
    pid = _seed_ready_participant(api_client, "API-006")
    response = api_client.get(f"/api/v1/participants/{pid}/status")
    assert response.status_code == 200
    body = response.json()
    assert body["prediction_available"] is False
    assert body["biological_clock"] is None


def test_get_status_does_not_create_a_circadian_label(api_client):
    pid = _seed_ready_participant(api_client, "API-007")
    api_client.get(f"/api/v1/participants/{pid}/status")
    api_client.get(f"/api/v1/participants/{pid}/status")

    session = api_client.app.state.session_factory()
    count = len(session.query(CircadianLabel).filter(CircadianLabel.participant_id == pid).all())
    session.close()
    assert count == 0  # GET must never trigger inference/persistence


# --- 4, 5, 6, 7. History / behavior / contributors / recommendation ---


def test_get_circadian_history_empty_but_valid(api_client):
    pid = _seed_ready_participant(api_client, "API-008")
    response = api_client.get(f"/api/v1/participants/{pid}/circadian/history")
    assert response.status_code == 200
    assert response.json()["entries"] == []


def test_get_behavior_history_returns_seeded_days(api_client):
    pid = _seed_ready_participant(api_client, "API-009", n_days=5)
    response = api_client.get(f"/api/v1/participants/{pid}/behavior")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 5
    assert body["entries"][0]["sleep_onset"] is not None


def test_record_daily_entry_creates_and_updates_observation(api_client):
    pid = _seed_ready_participant(api_client, "API-009B", n_days=0)
    entry_date = str(BASE_DATE + timedelta(days=30))

    create_response = api_client.post(
        f"/api/v1/participants/{pid}/behavior",
        json={"observation_date": entry_date, "sleep_onset_time": "23:15", "morning_light_duration_minutes": 25},
    )
    assert create_response.status_code == 201
    assert create_response.json()["saved"] is True

    history_response = api_client.get(f"/api/v1/participants/{pid}/behavior?start_date={entry_date}&end_date={entry_date}")
    entries = history_response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["sleep_onset"] == "23:15"
    assert entries[0]["morning_light_duration_minutes"] == 25

    update_response = api_client.post(
        f"/api/v1/participants/{pid}/behavior",
        json={"observation_date": entry_date, "sleep_onset_time": "23:30"},
    )
    assert update_response.status_code == 201
    history_after_update = api_client.get(f"/api/v1/participants/{pid}/behavior?start_date={entry_date}&end_date={entry_date}")
    assert history_after_update.json()["entries"][0]["sleep_onset"] == "23:30"
    assert history_after_update.json()["count"] == 1  # updated in place, not duplicated


def test_record_daily_entry_rejects_malformed_time(api_client):
    pid = _seed_ready_participant(api_client, "API-009C", n_days=0)
    response = api_client.post(
        f"/api/v1/participants/{pid}/behavior",
        json={"observation_date": str(BASE_DATE), "sleep_onset_time": "25:99"},
    )
    assert response.status_code == 422


def test_record_daily_entry_for_unknown_participant_is_404(api_client):
    response = api_client.post(
        "/api/v1/participants/999999/behavior",
        json={"observation_date": str(BASE_DATE), "sleep_onset_time": "23:00"},
    )
    assert response.status_code == 404


def test_get_contributors_404_without_a_result(api_client):
    pid = _seed_ready_participant(api_client, "API-010")
    response = api_client.get(f"/api/v1/participants/{pid}/contributors/current")
    assert response.status_code == 404


def test_get_recommendation_404_without_a_result(api_client):
    pid = _seed_ready_participant(api_client, "API-011")
    response = api_client.get(f"/api/v1/participants/{pid}/recommendation/current")
    assert response.status_code == 404


# --- 8, 9. Intervention history + outcome submission ---


def test_intervention_history_empty_initially(api_client):
    pid = _seed_ready_participant(api_client, "API-012")
    response = api_client.get(f"/api/v1/participants/{pid}/interventions")
    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_submit_outcome_for_unknown_log_is_404(api_client):
    pid = _seed_ready_participant(api_client, "API-013")
    response = api_client.post(
        f"/api/v1/participants/{pid}/interventions/999999/outcome",
        json={"observation_date": str(BASE_DATE), "actual_value_time": "22:00"},
    )
    assert response.status_code == 404


def test_submit_outcome_computes_compliance_via_phase12(api_client):
    _seed_recommendation_catalogue(api_client)
    pid = _seed_ready_participant(api_client, "API-014")

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

    response = api_client.post(
        f"/api/v1/participants/{pid}/interventions/{log_id}/outcome",
        json={"observation_date": str(BASE_DATE), "actual_value_time": "21:15"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["compliance_degree"] == pytest.approx(1.0)  # earlier than target -> full compliance


def test_submit_missing_observation_is_not_noncompliance(api_client):
    _seed_recommendation_catalogue(api_client)
    pid = _seed_ready_participant(api_client, "API-015")

    session = api_client.app.state.session_factory()
    recommendation = session.query(Recommendation).filter(Recommendation.intervention_type == "screen").first()
    log = InterventionLog(participant_id=pid, recommendation_id=recommendation.id, log_date=BASE_DATE, target_value_time=hour_to_clock_time(21.5))
    session.add(log)
    session.commit()
    log_id = log.id
    session.close()

    response = api_client.post(
        f"/api/v1/participants/{pid}/interventions/{log_id}/outcome",
        json={"observation_date": str(BASE_DATE), "observed": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is False
    assert body["compliance_degree"] is None
    assert body["compliance_binary"] is None  # unknown, not False


# --- 10. Safety endpoint ---


def test_safety_status_no_flags_initially(api_client):
    pid = _seed_ready_participant(api_client, "API-016")
    response = api_client.get(f"/api/v1/participants/{pid}/safety")
    assert response.status_code == 200
    body = response.json()
    assert body["active_flags"] == []
    assert body["highest_severity"] is None
    assert body["boundary_note"]


# --- 17, 18. Inference endpoint / idempotency ---


def test_inference_insufficient_history(api_client):
    pid = _seed_ready_participant(api_client, "API-017", n_days=3)
    response = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": str(BASE_DATE + timedelta(days=3))})
    assert response.status_code == 200
    body = response.json()
    assert body["pipeline_status"] == "INSUFFICIENT_HISTORY"


def test_inference_success_and_idempotency(api_client):
    pid = _seed_ready_participant(api_client, "API-018", n_days=7)
    target_date = str(BASE_DATE + timedelta(days=7))

    first = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": target_date})
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["pipeline_status"] == "SUCCESS"
    assert first_body["idempotent_short_circuit"] is False

    second = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": target_date})
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["idempotent_short_circuit"] is True

    session = api_client.app.state.session_factory()
    count = len(
        session.query(CircadianLabel)
        .filter(CircadianLabel.participant_id == pid, CircadianLabel.target_date == date.fromisoformat(target_date))
        .all()
    )
    session.close()
    assert count == 1  # no duplicate row from the second call


def test_status_reflects_committed_inference_result(api_client):
    pid = _seed_ready_participant(api_client, "API-019", n_days=7)
    target_date = str(BASE_DATE + timedelta(days=7))
    api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": target_date})

    response = api_client.get(f"/api/v1/participants/{pid}/status")
    assert response.status_code == 200
    body = response.json()
    assert body["prediction_available"] is True
    assert body["biological_clock"] is not None
    assert len(body["contributors"]) >= 1
    assert body["alignment"]["components"] is not None
    assert body["alignment"]["components"]["sleep_consistency"] is not None
    assert body["alignment"]["ideal_sleep_onset"] is not None


# --- 20. Safety suppression reflected in recommendation response ---


def test_high_severity_flag_suppresses_recommendation_response(api_client):
    pid = _seed_ready_participant(api_client, "API-020", n_days=7)
    target_date = BASE_DATE + timedelta(days=7)
    api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": str(target_date)})

    session = api_client.app.state.session_factory()
    label = session.query(CircadianLabel).filter(CircadianLabel.participant_id == pid, CircadianLabel.is_latest.is_(True)).first()
    label.safety_severity = "HIGH"
    label.recommendation_suppressed = True
    session.add(
        SafetyFlag(
            participant_id=pid, flagged_date=target_date, flag_type="continuous_dlmo_drift", severity="HIGH",
            message_shown="test", recommendation_suppressed=True,
        )
    )
    session.commit()
    session.close()

    response = api_client.get(f"/api/v1/participants/{pid}/recommendation/current")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["suppressed"] is True
    assert "healthcare professional" in body["safety_message"]

    status_response = api_client.get(f"/api/v1/participants/{pid}/status")
    assert status_response.json()["safety"]["highest_severity"] == "HIGH"
    assert status_response.json()["recommendation"]["suppressed"] is True


# --- 21, 22. No medical language / no raw database objects ---


def test_no_medical_language_in_status_response(api_client):
    pid = _seed_ready_participant(api_client, "API-021", n_days=7)
    api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": str(BASE_DATE + timedelta(days=7))})

    response = api_client.get(f"/api/v1/participants/{pid}/status")
    body_text = str(response.json()).lower()
    for banned in ("melatonin", "diagnos", "clinical dlmo", "prescri"):
        assert banned not in body_text


def test_response_never_contains_raw_sqlalchemy_repr(api_client):
    pid = _seed_ready_participant(api_client, "API-022")
    response = api_client.get(f"/api/v1/participants/{pid}")
    body_text = str(response.json())
    assert "<app.database.models" not in body_text
    assert "sqlalchemy" not in body_text.lower()


# --- 23. Centralized error handling ---


def test_error_response_shape_is_consistent(api_client):
    response = api_client.get("/api/v1/participants/999999")
    body = response.json()
    assert set(body.keys()) == {"error", "message", "detail", "correlation_id"}


# --- 24. Correlation ID ---


def test_correlation_id_present_in_response_header_and_body(api_client):
    response = api_client.get("/api/v1/participants/999999", headers={"X-Correlation-ID": "test-corr-123"})
    assert response.headers["X-Correlation-ID"] == "test-corr-123"
    assert response.json()["correlation_id"] == "test-corr-123"


def test_correlation_id_generated_when_absent(api_client):
    response = api_client.get("/api/v1/health")
    assert response.headers.get("X-Correlation-ID")


# --- OpenAPI docs availability ---


def test_openapi_docs_available(api_client):
    response = api_client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert "/api/v1/health" in spec["paths"]
    assert "/api/v1/participants/{participant_id}/status" in spec["paths"]

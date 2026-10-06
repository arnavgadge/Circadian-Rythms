"""AUDIT 19 -- API contract adversarial tests.

Covers: input validation (422 not 500), response schema conformance,
documented error taxonomy (404/409/503, no traceback leaks), safety
suppression propagation, no raw DB-object leakage, no side effects on
GET, idempotency, and no partial writes on a mid-transaction failure.

Reuses the ``api_client`` fixture from ``tests/conftest.py`` and the
seeding helpers already established in ``tests/test_api.py`` /
``tests/test_api_flows.py`` rather than reinventing DB setup.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.api.schemas.status import AlignmentComponents, StatusResponse
from app.api.schemas.inference import InferenceResponse
from app.database.models import CircadianLabel, DailyObservation, Participant, ParticipantProfile, SafetyFlag
from app.synthetic.time_utils import hour_to_clock_time

BASE_DATE = date(2026, 8, 1)


def _seed_ready_participant(client, code: str, n_days: int = 7) -> int:
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


# --- 1. Input validation: malformed/missing POST bodies -> 422 not 500 ---


def test_inference_malformed_date_returns_422(api_client):
    pid = _seed_ready_participant(api_client, "AUD-001")
    response = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": "not-a-date"})
    assert response.status_code == 422


def test_inference_wrong_type_for_force_rerun_returns_422(api_client):
    pid = _seed_ready_participant(api_client, "AUD-002")
    response = api_client.post(f"/api/v1/participants/{pid}/inference", json={"force_rerun": "not-a-bool"})
    assert response.status_code == 422


def test_inference_non_integer_participant_id_returns_422(api_client):
    response = api_client.post("/api/v1/participants/not-an-int/inference", json={})
    assert response.status_code == 422


def test_inference_target_date_as_wrong_type_returns_422(api_client):
    pid = _seed_ready_participant(api_client, "AUD-003")
    response = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": 12345})
    assert response.status_code == 422


# --- 2. Response schema conformance: exact field sets ---


def test_status_response_has_exactly_declared_fields(api_client):
    pid = _seed_ready_participant(api_client, "AUD-004", n_days=7)
    api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": str(BASE_DATE + timedelta(days=7))})

    response = api_client.get(f"/api/v1/participants/{pid}/status")
    assert response.status_code == 200
    body = response.json()

    assert set(body.keys()) == set(StatusResponse.model_fields.keys())
    assert body["alignment"]["components"] is not None
    assert set(body["alignment"]["components"].keys()) == set(AlignmentComponents.model_fields.keys())


def test_inference_response_has_exactly_declared_fields(api_client):
    pid = _seed_ready_participant(api_client, "AUD-005", n_days=7)
    response = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": str(BASE_DATE + timedelta(days=7))})
    assert response.status_code == 200
    body = response.json()

    assert set(body.keys()) == set(InferenceResponse.model_fields.keys())
    assert set(body["status"].keys()) == set(StatusResponse.model_fields.keys())


# --- 3. Error taxonomy: 404, 409, and hidden-exception -> documented code, no leak ---


def test_nonexistent_participant_status_returns_404(api_client):
    response = api_client.get("/api/v1/participants/999999/status")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "notfound"
    assert "correlation_id" in body


def test_duplicate_participant_code_returns_409(api_client):
    api_client.post("/api/v1/participants", json={"participant_code": "AUD-DUP"})
    response = api_client.post("/api/v1/participants", json={"participant_code": "AUD-DUP"})
    assert response.status_code == 409
    assert response.json()["error"] == "conflict"


def test_unexpected_exception_surfaces_as_500_without_leaking_traceback(api_client, monkeypatch):
    pid = _seed_ready_participant(api_client, "AUD-006")

    def _boom(self, participant_id, target_date=None):
        raise RuntimeError("boom-secret-internal-detail /some/real/path.py line 42")

    from app.api.services.status_service import StatusService
    from starlette.testclient import TestClient

    monkeypatch.setattr(StatusService, "build_status", _boom)

    # raise_server_exceptions=False: we want the client-visible mapped
    # response (as a real deployed client would see it), not pytest's
    # usual re-raise-for-debugging behavior.
    with TestClient(api_client.app, raise_server_exceptions=False) as client:
        response = client.get(f"/api/v1/participants/{pid}/status")

    assert response.status_code == 500
    body = response.json()
    text = response.text
    assert body["error"] == "internal_error"
    assert "RuntimeError" not in text
    assert "boom-secret-internal-detail" not in text
    assert "/some/real/path.py" not in text
    assert "Traceback" not in text


def test_db_layer_read_failure_surfaces_as_503_without_leaking_raw_message(api_client, monkeypatch):
    """Regression for the orchestrator "read" stage split (read vs
    read_infrastructure): a real DB-layer error during the read step
    must map to a generic 503 with a stage-only detail, never a 404
    carrying the raw exception text (that path is only for
    deliberately-authored ValueErrors from app.pipeline.read)."""
    pid = _seed_ready_participant(api_client, "AUD-007")

    from sqlalchemy.exc import OperationalError

    import app.pipeline.orchestrator as orchestrator_module

    def _boom(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("simulated connection lost -- secret/internal/detail"))

    monkeypatch.setattr(orchestrator_module, "read_daily_inference_inputs", _boom)

    response = api_client.post(f"/api/v1/participants/{pid}/inference", json={})

    assert response.status_code == 503
    body = response.json()
    text = response.text
    assert "secret/internal/detail" not in text
    assert "simulated connection lost" not in text
    assert "OperationalError" not in text
    assert body["detail"] == "stage=read_infrastructure"


# --- 4. Safety propagation: suppression is surfaced, not dropped ---


def test_status_reflects_recommendation_suppression(api_client):
    pid = _seed_ready_participant(api_client, "AUD-007", n_days=7)
    target_date = BASE_DATE + timedelta(days=7)
    inference_response = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": str(target_date)})
    assert inference_response.status_code == 200

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

    status_response = api_client.get(f"/api/v1/participants/{pid}/status")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["recommendation"]["suppressed"] is True
    assert body["recommendation"]["available"] is False
    assert body["safety"]["recommendation_suppressed"] is True
    assert body["safety"]["highest_severity"] == "HIGH"


# --- 5. No raw DB objects leak ---


def test_participant_and_status_responses_have_no_sqlalchemy_leakage(api_client):
    pid = _seed_ready_participant(api_client, "AUD-008", n_days=7)
    api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": str(BASE_DATE + timedelta(days=7))})

    for path in (f"/api/v1/participants/{pid}", f"/api/v1/participants/{pid}/status"):
        response = api_client.get(path)
        assert response.status_code == 200
        text = response.text
        assert "_sa_instance_state" not in text
        assert "object at 0x" not in text
        assert "sqlalchemy" not in text.lower()

        def _check_primitive(value):
            if isinstance(value, dict):
                for v in value.values():
                    _check_primitive(v)
            elif isinstance(value, list):
                for v in value:
                    _check_primitive(v)
            else:
                assert value is None or isinstance(value, (str, int, float, bool))

        _check_primitive(response.json())


# --- 6. No unintended side effects on GET; POST does write ---


def test_get_status_does_not_write_but_post_inference_does(api_client):
    pid = _seed_ready_participant(api_client, "AUD-009", n_days=7)

    session = api_client.app.state.session_factory()
    before = session.query(CircadianLabel).filter(CircadianLabel.participant_id == pid).count()
    session.close()
    assert before == 0

    api_client.get(f"/api/v1/participants/{pid}/status")
    api_client.get(f"/api/v1/participants/{pid}/status")

    session = api_client.app.state.session_factory()
    after_get = session.query(CircadianLabel).filter(CircadianLabel.participant_id == pid).count()
    session.close()
    assert after_get == 0  # GET must never write

    target_date = str(BASE_DATE + timedelta(days=7))
    response = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": target_date})
    assert response.status_code == 200

    session = api_client.app.state.session_factory()
    after_post = session.query(CircadianLabel).filter(CircadianLabel.participant_id == pid).count()
    session.close()
    assert after_post == 1  # POST does write


# --- 7. Idempotency: repeated POST does not duplicate or change the result ---


def test_inference_idempotency_no_duplicate_and_same_result(api_client):
    pid = _seed_ready_participant(api_client, "AUD-010", n_days=7)
    target_date = str(BASE_DATE + timedelta(days=7))

    first = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": target_date})
    second = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": target_date})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["idempotent_short_circuit"] is False
    assert second.json()["idempotent_short_circuit"] is True
    assert first.json()["status"]["biological_clock"] == second.json()["status"]["biological_clock"]

    session = api_client.app.state.session_factory()
    matching = session.query(CircadianLabel).filter(
        CircadianLabel.participant_id == pid, CircadianLabel.target_date == date.fromisoformat(target_date)
    ).all()
    session.close()
    assert len(matching) == 1


# --- 8. No partial writes on a mid-transaction failure ---


def test_inference_mid_transaction_failure_rolls_back_fully(api_client, monkeypatch):
    pid = _seed_ready_participant(api_client, "AUD-011", n_days=7)
    target_date = str(BASE_DATE + timedelta(days=7))

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated persistence failure mid-transaction")

    monkeypatch.setattr("app.pipeline.orchestrator.write_alignment_and_contributors", _boom)

    response = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": target_date})

    # Documented mapping: an unclassified pipeline failure -> DependencyUnavailableError -> 503.
    assert response.status_code == 503
    body = response.json()
    text = response.text
    assert "RuntimeError" not in text
    assert "simulated persistence failure" not in text
    assert "Traceback" not in text
    assert body["error"] == "dependencyunavailable"
    assert body["detail"] == "stage=persistence"

    session = api_client.app.state.session_factory()
    remaining = session.query(CircadianLabel).filter(
        CircadianLabel.participant_id == pid, CircadianLabel.target_date == date.fromisoformat(target_date)
    ).all()
    session.close()
    assert len(remaining) == 0  # whole write transaction must have rolled back, no partial row

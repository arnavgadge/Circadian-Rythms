"""AUDIT 23 -- Failure injection into the Phase 11 daily inference
pipeline (``app.pipeline.orchestrator.run_daily_inference``).

Each of the 8 documented/implied failure points is exercised by
monkeypatching the function reference *as imported into
``app.pipeline.orchestrator``'s namespace* (not its origin module),
per standard ``unittest.mock`` practice. For every case we assert:

- the documented outcome (graceful ``FAILED`` result, or documented
  graceful degradation for XGBoost) rather than an unhandled crash,
- nothing is partially written when the outcome is failure,
- something is logged at ERROR level,
- (for two representative cases) the API layer returns a safe JSON
  error body that never leaks the raw exception text/type.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.database.models import (
    AlignmentResult,
    CircadianLabel,
    InterventionLog,
    Participant,
    Recommendation,
)
from app.database.seed import seed_reference_data
from app.pipeline import orchestrator as orchestrator_module
from app.pipeline.orchestrator import run_daily_inference
from app.pipeline.types import FAILED, INSUFFICIENT_HISTORY, NO_PREDICTION, SUCCESS


@pytest.fixture
def pipeline_session_factory(db_session_factory, small_synthetic_dataset):
    session = db_session_factory()
    seed_reference_data(session)
    session.close()
    return db_session_factory


def _first_participant_id(session_factory) -> int:
    session = session_factory()
    try:
        return session.execute(select(Participant.id).order_by(Participant.id)).scalars().first()
    finally:
        session.close()


def _observation_dates(session_factory, participant_id: int) -> list:
    from app.database.models import DailyObservation

    session = session_factory()
    try:
        return list(
            session.execute(
                select(DailyObservation.observation_date)
                .where(DailyObservation.participant_id == participant_id)
                .order_by(DailyObservation.observation_date)
            ).scalars().all()
        )
    finally:
        session.close()


def _label_row_count(session_factory, participant_id: int, target_date: date) -> int:
    """Total ``circadian_labels`` rows for participant/date, regardless
    of status -- used to prove "nothing was written" with no blind
    spots (including partially-committed rows a bug might leave)."""

    session = session_factory()
    try:
        return len(
            session.execute(
                select(CircadianLabel).where(
                    CircadianLabel.participant_id == participant_id,
                    CircadianLabel.target_date == target_date,
                )
            ).scalars().all()
        )
    finally:
        session.close()


def _related_table_counts(session_factory, participant_id: int, target_date: date) -> dict:
    session = session_factory()
    try:
        alignment_count = len(
            session.execute(
                select(AlignmentResult).join(CircadianLabel).where(
                    CircadianLabel.participant_id == participant_id,
                    CircadianLabel.target_date == target_date,
                )
            ).scalars().all()
        )
        intervention_log_count = len(
            session.execute(
                select(InterventionLog).where(
                    InterventionLog.participant_id == participant_id,
                    InterventionLog.log_date == target_date,
                )
            ).scalars().all()
        )
        return {"alignment_results": alignment_count, "intervention_logs": intervention_log_count}
    finally:
        session.close()


@pytest.fixture
def target(pipeline_session_factory):
    """(participant_id, target_date) with exactly 6 prior complete days,
    i.e. the first date sufficient-history/full-pipeline predictions run."""

    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    return pid, dates[6]


# ---------------------------------------------------------------------
# 1. Database / read failure
# ---------------------------------------------------------------------


def test_1_database_read_failure_returns_failed_not_a_crash(pipeline_session_factory, target, monkeypatch, caplog):
    pid, target_date = target
    before = _label_row_count(pipeline_session_factory, pid, target_date)

    def _boom(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("simulated connection lost"))

    monkeypatch.setattr(orchestrator_module, "read_daily_inference_inputs", _boom)

    with caplog.at_level(logging.ERROR):
        result = run_daily_inference(pid, target_date, pipeline_session_factory)

    assert result.status == FAILED
    # A real DB-layer error (not a deliberately-authored ValueError from
    # app.pipeline.read) lands on "read_infrastructure", a distinct stage
    # from "read" -- so the API layer never forwards its raw message to a
    # client (see app/api/services/inference_service.py).
    assert result.failure_stage == "read_infrastructure"
    assert _label_row_count(pipeline_session_factory, pid, target_date) == before
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# ---------------------------------------------------------------------
# 2. Model-loading / XGBoost failure -- documented GRACEFUL degradation
# ---------------------------------------------------------------------


def test_2_xgboost_failure_degrades_to_state_only_fusion_not_pipeline_failure(
    pipeline_session_factory, target, monkeypatch, caplog
):
    pid, target_date = target
    before = _label_row_count(pipeline_session_factory, pid, target_date)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated model-loading failure")

    monkeypatch.setattr(orchestrator_module, "run_xgboost_step", _boom)

    with caplog.at_level(logging.ERROR):
        result = run_daily_inference(pid, target_date, pipeline_session_factory)

    # Per the orchestrator's own documented policy: NOT a pipeline
    # failure. XGBoost is simply unavailable this run.
    assert result.status != FAILED
    assert result.status in (SUCCESS, NO_PREDICTION, INSUFFICIENT_HISTORY)
    assert result.xgb_prediction is None
    assert result.fusion_result is not None
    assert result.fusion_result.xgb_available is False
    assert result.fusion_result.state_available is True
    assert result.persistence_status == "committed"
    assert _label_row_count(pipeline_session_factory, pid, target_date) == before + 1
    # The failure is still logged (not silently swallowed), just not
    # surfaced as an overall pipeline failure.
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# ---------------------------------------------------------------------
# 3. Feature-generation failure
# ---------------------------------------------------------------------


def test_3_feature_generation_failure_fails_pipeline_nothing_written(pipeline_session_factory, target, monkeypatch, caplog):
    pid, target_date = target
    before = _label_row_count(pipeline_session_factory, pid, target_date)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated feature-engine failure")

    monkeypatch.setattr(orchestrator_module, "build_feature_step", _boom)

    with caplog.at_level(logging.ERROR):
        result = run_daily_inference(pid, target_date, pipeline_session_factory)

    assert result.status == FAILED
    assert result.failure_stage == "feature_engine"
    assert _label_row_count(pipeline_session_factory, pid, target_date) == before
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# ---------------------------------------------------------------------
# 4. State-engine failure
# ---------------------------------------------------------------------


def test_4_state_engine_failure_degrades_gracefully_not_a_crash(pipeline_session_factory, target, monkeypatch, caplog):
    pid, target_date = target
    before = _label_row_count(pipeline_session_factory, pid, target_date)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated state-engine failure")

    monkeypatch.setattr(orchestrator_module, "run_state_step", _boom)

    with caplog.at_level(logging.ERROR):
        # Before the fix this raised RuntimeError straight out of
        # run_daily_inference (unhandled) -- genuine defect, fixed by
        # wrapping the state-engine call in the same try/except-and-_fail
        # pattern the feature-engine step already uses.
        result = run_daily_inference(pid, target_date, pipeline_session_factory)

    assert result.status == FAILED
    assert result.failure_stage == "state_engine"
    assert _label_row_count(pipeline_session_factory, pid, target_date) == before
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# ---------------------------------------------------------------------
# 5. Fusion failure
# ---------------------------------------------------------------------


def test_5_fusion_failure_degrades_gracefully_not_a_crash(pipeline_session_factory, target, monkeypatch, caplog):
    pid, target_date = target
    before = _label_row_count(pipeline_session_factory, pid, target_date)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated fusion failure")

    monkeypatch.setattr(orchestrator_module, "fuse", _boom)

    with caplog.at_level(logging.ERROR):
        result = run_daily_inference(pid, target_date, pipeline_session_factory)

    assert result.status == FAILED
    assert result.failure_stage == "fusion"
    assert _label_row_count(pipeline_session_factory, pid, target_date) == before
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# ---------------------------------------------------------------------
# 6. Alignment failure
# ---------------------------------------------------------------------


def test_6_alignment_failure_fails_pipeline_nothing_written(pipeline_session_factory, target, monkeypatch, caplog):
    pid, target_date = target
    before = _label_row_count(pipeline_session_factory, pid, target_date)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated alignment failure")

    monkeypatch.setattr(orchestrator_module, "compute_alignment", _boom)

    with caplog.at_level(logging.ERROR):
        result = run_daily_inference(pid, target_date, pipeline_session_factory)

    assert result.status == FAILED
    assert result.failure_stage == "alignment_contributor_recommendation"
    assert _label_row_count(pipeline_session_factory, pid, target_date) == before
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# ---------------------------------------------------------------------
# 7. Recommendation failure
# ---------------------------------------------------------------------


def test_7_recommendation_failure_fails_pipeline_nothing_written(pipeline_session_factory, target, monkeypatch, caplog):
    pid, target_date = target
    before = _label_row_count(pipeline_session_factory, pid, target_date)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated recommendation-engine failure")

    monkeypatch.setattr(orchestrator_module, "select_recommendations", _boom)

    with caplog.at_level(logging.ERROR):
        result = run_daily_inference(pid, target_date, pipeline_session_factory)

    assert result.status == FAILED
    assert result.failure_stage == "alignment_contributor_recommendation"
    assert _label_row_count(pipeline_session_factory, pid, target_date) == before
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# ---------------------------------------------------------------------
# 8. Database-write / persistence failure -- full-rollback, no partial writes
# ---------------------------------------------------------------------


def test_8_write_failure_rolls_back_fully_no_partial_rows(pipeline_session_factory, target, monkeypatch, caplog):
    pid, target_date = target
    before_labels = _label_row_count(pipeline_session_factory, pid, target_date)
    before_related = _related_table_counts(pipeline_session_factory, pid, target_date)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated write failure partway through the transaction")

    # write_alignment_and_contributors runs *after* write_circadian_label
    # inside the same transaction -- failing here (rather than on the
    # very first write) is the more rigorous check that a partially
    # written label row does not survive rollback.
    monkeypatch.setattr(orchestrator_module, "write_alignment_and_contributors", _boom)

    with caplog.at_level(logging.ERROR):
        result = run_daily_inference(pid, target_date, pipeline_session_factory)

    assert result.status == FAILED
    assert result.failure_stage == "persistence"
    assert result.persistence_status == "not_attempted"

    # The most important assertion in this file: full rollback, not a
    # partial commit, across every table the transaction touches.
    assert _label_row_count(pipeline_session_factory, pid, target_date) == before_labels
    after_related = _related_table_counts(pipeline_session_factory, pid, target_date)
    assert after_related == before_related

    session = pipeline_session_factory()
    try:
        from app.database.models import ParticipantProfile

        profile = session.get(ParticipantProfile, pid)
        assert profile.current_dlmo_date != target_date  # profile state never partially updated
    finally:
        session.close()

    assert any(r.levelno >= logging.ERROR for r in caplog.records)


def test_8b_write_failure_on_first_write_also_rolls_back(pipeline_session_factory, target, monkeypatch, caplog):
    """Same as case 8 but failing on the very first statement inside the
    transaction (``write_circadian_label``), to rule out an
    order-dependent partial-commit bug."""

    pid, target_date = target
    before = _label_row_count(pipeline_session_factory, pid, target_date)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated write failure on first write")

    monkeypatch.setattr(orchestrator_module, "write_circadian_label", _boom)

    with caplog.at_level(logging.ERROR):
        result = run_daily_inference(pid, target_date, pipeline_session_factory)

    assert result.status == FAILED
    assert result.failure_stage == "persistence"
    assert _label_row_count(pipeline_session_factory, pid, target_date) == before
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


# ---------------------------------------------------------------------
# API-level: representative cases must never leak raw exception text
# ---------------------------------------------------------------------


def _forbidden_leak_strings():
    return ("Traceback", "RuntimeError", "OperationalError", ".py\"", ".py:", "site-packages", "File \"")


def test_api_persistence_failure_returns_safe_503_no_leak(api_client, monkeypatch):
    from datetime import timedelta

    from tests.test_api_flows import BASE_DATE, _seed_full_participant

    pid = _seed_full_participant(api_client, "AUDIT23-P1")
    target_date = str(BASE_DATE + timedelta(days=7))

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(orchestrator_module, "write_recommendation", _boom)

    response = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": target_date})

    assert response.status_code in (500, 503)
    body_text = response.text
    # The centralized error handler forwards a short application-level
    # message (see app.api.errors's docstring) but must never forward a
    # raw traceback, exception class name, or interpreter source path.
    for forbidden in _forbidden_leak_strings():
        assert forbidden not in body_text


def test_api_state_engine_failure_returns_safe_response_no_leak(api_client, monkeypatch):
    """Representative test for the unhandled-exception class of failure
    (state-engine / fusion): even before any orchestrator-level fix,
    the API's blanket ``Exception`` handler must still turn this into a
    safe JSON 500, never a raw traceback to the client."""

    from datetime import timedelta

    from tests.test_api_flows import BASE_DATE, _seed_full_participant

    pid = _seed_full_participant(api_client, "AUDIT23-P2")
    target_date = str(BASE_DATE + timedelta(days=7))

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated state-engine failure")

    monkeypatch.setattr(orchestrator_module, "run_state_step", _boom)

    response = api_client.post(f"/api/v1/participants/{pid}/inference", json={"target_date": target_date})

    assert response.status_code in (400, 404, 500, 503)
    body_text = response.text
    for forbidden in _forbidden_leak_strings():
        assert forbidden not in body_text

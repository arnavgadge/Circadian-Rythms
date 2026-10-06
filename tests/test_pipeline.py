"""End-to-end tests for the Phase 11 daily inference pipeline."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete, select

from app.database.models import (
    CircadianLabel,
    DailyObservation,
    InterventionLog,
    Participant,
    ParticipantProfile,
    Recommendation,
)
from app.database.seed import seed_reference_data
from app.pipeline import orchestrator as orchestrator_module
from app.pipeline.orchestrator import run_daily_inference
from app.pipeline.read import read_daily_inference_inputs
from app.pipeline.types import FAILED, INSUFFICIENT_HISTORY, SUCCESS
from app.synthetic.time_utils import clock_time_to_hour


@pytest.fixture
def pipeline_session_factory(db_session_factory, small_synthetic_dataset):
    """The standard 5-participant x 30-day synthetic fixture, plus the
    Phase 10 intervention catalogue seeded so recommendations can be
    selected end-to-end."""

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


_PIPELINE_STATUSES = ("success", "insufficient_history", "no_prediction")


def _label_count(session_factory, participant_id: int, target_date: date) -> int:
    """How many rows *this pipeline* has written for participant/date --
    excludes the Phase 3 synthetic ``synthetic_ground_truth`` seed row
    the fixture pre-populates for every day, which is reference data,
    not a prior pipeline run (see orchestrator's ``_PIPELINE_OWNED_STATUSES``).
    """

    session = session_factory()
    try:
        return len(
            session.execute(
                select(CircadianLabel).where(
                    CircadianLabel.participant_id == participant_id,
                    CircadianLabel.target_date == target_date,
                    CircadianLabel.prediction_status.in_(_PIPELINE_STATUSES),
                )
            ).scalars().all()
        )
    finally:
        session.close()


# --- 1. Successful end-to-end inference ---


def test_successful_end_to_end_inference(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]  # Day 7: 6 prior complete days (dates[0:6]) exist

    result = run_daily_inference(pid, target_date, pipeline_session_factory)

    assert result.status == SUCCESS
    assert result.persistence_status == "committed"
    assert result.xgb_prediction is not None
    assert result.fusion_result is not None and result.fusion_result.fused_final is not None
    assert result.alignment_result is not None
    assert result.contributor_result is not None
    assert result.recommendation_result is not None
    assert result.circadian_label_id is not None


# --- 2. Six-day window correctness / 3. no target-day leakage ---


def test_six_day_window_matches_days_1_through_6_for_day_7_prediction(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]

    session = pipeline_session_factory()
    try:
        read_result = read_daily_inference_inputs(session, pid, target_date)
    finally:
        session.close()

    assert [o.observation_date for o in read_result.window_observations] == dates[0:6]
    assert all(o.observation_date < target_date for o in read_result.window_observations)


def test_day_8_uses_days_2_through_7_and_day_9_uses_days_3_through_8(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    session = pipeline_session_factory()
    try:
        read_day8 = read_daily_inference_inputs(session, pid, dates[7])
        read_day9 = read_daily_inference_inputs(session, pid, dates[8])
    finally:
        session.close()

    assert [o.observation_date for o in read_day8.window_observations] == dates[1:7]
    assert [o.observation_date for o in read_day9.window_observations] == dates[2:8]


def test_target_day_behavior_cannot_affect_its_own_prediction(pipeline_session_factory):
    # Tested at the feature-vector level (not the full pipeline level):
    # re-running the full pipeline twice legitimately advances the
    # state engine between calls (a real, expected side effect), which
    # would confound a full-result diff. The no-leakage guarantee is
    # specifically about Phase 4's feature window, so that is what is
    # compared directly.
    from app.pipeline.xgboost_step import build_feature_step

    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]

    session = pipeline_session_factory()
    try:
        features_before = build_feature_step(pid, target_date, session).feature_vector.features.copy()
    finally:
        session.close()

    session = pipeline_session_factory()
    try:
        target_obs = session.execute(
            select(DailyObservation).where(
                DailyObservation.participant_id == pid, DailyObservation.observation_date == target_date
            )
        ).scalars().one()
        target_obs.evening_screen_duration_minutes = 999.0
        session.commit()
    finally:
        session.close()

    session = pipeline_session_factory()
    try:
        features_after = build_feature_step(pid, target_date, session).feature_vector.features.copy()
    finally:
        session.close()

    assert features_before == pytest.approx(features_after)


# --- 4. Insufficient history ---


def test_insufficient_history_before_day_7(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[3]  # only 3 prior complete days

    result = run_daily_inference(pid, target_date, pipeline_session_factory)

    assert result.status == INSUFFICIENT_HISTORY
    assert result.xgb_prediction is None
    assert result.state_prediction is not None  # state equation still runs


# --- 5. XGBoost integration ---


def test_xgboost_prediction_present_and_bounded_for_sufficient_history(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    result = run_daily_inference(pid, dates[6], pipeline_session_factory)

    assert result.xgb_prediction is not None
    assert 0.0 <= result.xgb_prediction["xgb_dlmo_hour"] < 24.0
    assert result.xgb_prediction["model_version"] == 1


# --- 6. State-engine integration ---


def test_state_engine_steps_forward_when_behavior_available(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    result = run_daily_inference(pid, dates[6], pipeline_session_factory)

    assert result.state_prediction["was_updated"] is True
    assert 0.0 <= result.state_prediction["state_dlmo_hour"] < 24.0


# --- 7. Fusion integration ---


def test_fusion_result_reflects_both_estimators_available(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    result = run_daily_inference(pid, dates[6], pipeline_session_factory)

    assert result.fusion_result.xgb_available is True
    assert result.fusion_result.state_available is True
    assert result.fusion_result.prediction_made is True


# --- 8. Alignment integration ---


def test_alignment_score_within_bounds(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    result = run_daily_inference(pid, dates[6], pipeline_session_factory)

    assert 0.0 <= result.alignment_result.final_score <= 100.0


# --- 9. Contributor integration ---


def test_contributor_result_has_ranked_candidates(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    result = run_daily_inference(pid, dates[6], pipeline_session_factory)

    assert len(result.contributor_result.all_candidates) == 5
    assert len(result.contributor_result.contributors) <= 3


# --- 10. Recommendation integration ---


def test_recommendation_result_has_at_most_one_primary(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    result = run_daily_inference(pid, dates[6], pipeline_session_factory)

    assert result.recommendation_result.primary is None or result.recommendation_result.primary.priority == 1
    assert len(result.recommendation_result.supporting) <= 2


# --- 11. Participant state update ---


def test_participant_state_updated_after_success(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]

    session = pipeline_session_factory()
    try:
        intrinsic_before = session.get(ParticipantProfile, pid).intrinsic_dlmo_time
    finally:
        session.close()

    result = run_daily_inference(pid, target_date, pipeline_session_factory)

    session = pipeline_session_factory()
    try:
        profile = session.get(ParticipantProfile, pid)
        assert clock_time_to_hour(profile.current_dlmo_time) == pytest.approx(result.fusion_result.fused_final, abs=1e-3)
        assert profile.current_dlmo_date == target_date
        assert profile.intrinsic_dlmo_time == intrinsic_before  # never touched
        assert clock_time_to_hour(profile.adapted_dlmo_time) == pytest.approx(
            result.participant_state_update.new_adapted_dlmo_hour, abs=1e-3
        )
        assert profile.current_alignment_score == pytest.approx(result.alignment_result.final_score, abs=1e-6)
    finally:
        session.close()


# --- 12. Atomic transaction / 22. no partial writes ---


def test_atomic_write_creates_all_rows_together(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]
    run_daily_inference(pid, target_date, pipeline_session_factory)

    session = pipeline_session_factory()
    try:
        label = session.execute(
            select(CircadianLabel).where(
                CircadianLabel.participant_id == pid, CircadianLabel.target_date == target_date,
                CircadianLabel.is_latest.is_(True),
            )
        ).scalars().one()
        assert label.alignment_result is not None
        assert len(label.alignment_result.contributors) >= 1
    finally:
        session.close()


# --- 13. Rollback ---


def test_write_failure_rolls_back_entire_transaction(pipeline_session_factory, monkeypatch):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(orchestrator_module, "write_recommendation", _boom)

    result = run_daily_inference(pid, target_date, pipeline_session_factory)

    assert result.status == FAILED
    assert result.failure_stage == "persistence"
    assert result.persistence_status == "not_attempted"
    assert _label_count(pipeline_session_factory, pid, target_date) == 0

    session = pipeline_session_factory()
    try:
        profile = session.get(ParticipantProfile, pid)
        assert profile.current_dlmo_date != target_date  # never partially updated
    finally:
        session.close()


# --- 14. Idempotency / 15. retry behavior ---


def test_running_inference_twice_does_not_duplicate_records(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]

    first = run_daily_inference(pid, target_date, pipeline_session_factory)
    second = run_daily_inference(pid, target_date, pipeline_session_factory)

    assert first.idempotent_short_circuit is False
    assert second.idempotent_short_circuit is True
    assert _label_count(pipeline_session_factory, pid, target_date) == 1

    session = pipeline_session_factory()
    try:
        rec_count = len(
            session.execute(
                select(InterventionLog).where(
                    InterventionLog.participant_id == pid, InterventionLog.log_date == target_date
                )
            ).scalars().all()
        )
    finally:
        session.close()
    assert rec_count <= 1


def test_retry_after_failure_succeeds_without_duplicate(pipeline_session_factory, monkeypatch):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated transient failure")

    monkeypatch.setattr(orchestrator_module, "write_recommendation", _boom)
    failed_result = run_daily_inference(pid, target_date, pipeline_session_factory)
    assert failed_result.status == FAILED
    assert _label_count(pipeline_session_factory, pid, target_date) == 0

    monkeypatch.undo()
    retried_result = run_daily_inference(pid, target_date, pipeline_session_factory)
    assert retried_result.status == SUCCESS
    assert _label_count(pipeline_session_factory, pid, target_date) == 1


# --- 16. Model/version provenance ---


def test_provenance_diagnostics_present(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    result = run_daily_inference(pid, dates[6], pipeline_session_factory)

    provenance = result.diagnostics["provenance"]
    for key in (
        "pipeline_version", "feature_manifest_version", "model_version", "state_config_version",
        "fusion_config_version", "alignment_config_version", "contributor_config_version",
        "recommendation_config_version",
    ):
        assert key in provenance and provenance[key] is not None


# --- 17. Deterministic replay ---


def test_deterministic_replay_produces_same_fused_dlmo(pipeline_session_factory):
    # A true replay is "same database snapshot in, same result out" --
    # since a real run legitimately advances participant state as a
    # side effect, the profile's current/adapted state (and the
    # written label) is restored to its pre-run snapshot before the
    # second call, so both calls see an identical starting snapshot.
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]

    session = pipeline_session_factory()
    try:
        profile = session.get(ParticipantProfile, pid)
        snapshot = (profile.current_dlmo_time, profile.current_dlmo_date, profile.adapted_dlmo_time, profile.current_alignment_score, profile.current_alignment_date)
    finally:
        session.close()

    result_a = run_daily_inference(pid, target_date, pipeline_session_factory, force_rerun=True)

    session = pipeline_session_factory()
    try:
        session.execute(
            delete(CircadianLabel).where(
                CircadianLabel.participant_id == pid, CircadianLabel.target_date == target_date
            )
        )
        profile = session.get(ParticipantProfile, pid)
        (
            profile.current_dlmo_time, profile.current_dlmo_date, profile.adapted_dlmo_time,
            profile.current_alignment_score, profile.current_alignment_date,
        ) = snapshot
        session.commit()
    finally:
        session.close()

    result_b = run_daily_inference(pid, target_date, pipeline_session_factory, force_rerun=True)

    assert result_a.fusion_result.fused_final == pytest.approx(result_b.fusion_result.fused_final, abs=1e-9)
    assert result_a.alignment_result.final_score == pytest.approx(result_b.alignment_result.final_score, abs=1e-9)


# --- 18. Database result consistency ---


def test_committed_label_matches_returned_fusion_result(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]
    result = run_daily_inference(pid, target_date, pipeline_session_factory)

    session = pipeline_session_factory()
    try:
        label = session.get(CircadianLabel, result.circadian_label_id)
        assert clock_time_to_hour(label.fused_dlmo_time) == pytest.approx(result.fusion_result.fused_final, abs=1e-3)
        assert label.is_latest is True
    finally:
        session.close()


# --- 19. Recommendation persistence ---


def test_exactly_one_recommendation_record_referencing_a_real_intervention(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]
    result = run_daily_inference(pid, target_date, pipeline_session_factory)

    session = pipeline_session_factory()
    try:
        logs = session.execute(
            select(InterventionLog).where(
                InterventionLog.participant_id == pid, InterventionLog.log_date == target_date
            )
        ).scalars().all()
        if result.recommendation_result.primary is not None:
            assert len(logs) == 1
            recommendation = session.get(Recommendation, logs[0].recommendation_id)
            assert recommendation is not None
        else:
            assert len(logs) == 0
    finally:
        session.close()


# --- 20. Current-vs-historical state consistency ---


def test_current_state_matches_latest_historical_label(pipeline_session_factory):
    pid = _first_participant_id(pipeline_session_factory)
    dates = _observation_dates(pipeline_session_factory, pid)
    target_date = dates[6]
    run_daily_inference(pid, target_date, pipeline_session_factory)

    session = pipeline_session_factory()
    try:
        profile = session.get(ParticipantProfile, pid)
        label = session.execute(
            select(CircadianLabel).where(
                CircadianLabel.participant_id == pid, CircadianLabel.target_date == target_date,
                CircadianLabel.is_latest.is_(True),
            )
        ).scalars().one()
        assert clock_time_to_hour(profile.current_dlmo_time) == pytest.approx(clock_time_to_hour(label.fused_dlmo_time), abs=1e-6)
    finally:
        session.close()


# --- 21. Failure-stage reporting ---


def test_unknown_participant_reports_read_failure_stage(pipeline_session_factory):
    result = run_daily_inference(999_999_999, date(2025, 1, 1), pipeline_session_factory)
    assert result.status == FAILED
    assert result.failure_stage == "read"

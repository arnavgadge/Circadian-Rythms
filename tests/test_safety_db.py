"""Database-integration / scenario tests for the Phase 14 safety layer."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.database.models import (
    AlignmentResult,
    CircadianLabel,
    InterventionLog,
    Participant,
    ParticipantProfile,
    Recommendation,
    SafetyFlag,
)
from app.fusion.config import ConfidenceLabel
from app.safety.config import DEFAULT_SAFETY_CONFIG
from app.safety.engine import RecommendationInput, SafetyEngine
from app.safety.enums import HIGH, MODERATE, STATUS_FLAGGED, STATUS_INSUFFICIENT_DATA, STATUS_OK
from app.safety.guardrails import scan_for_prohibited_language
from app.safety.sanity import run_sanity_checks
from app.synthetic.time_utils import hour_to_clock_time

BASE_DATE = date(2026, 5, 1)


def _fusion_result(**overrides):
    defaults = dict(prediction_made=True, fused_final=21.75, final_confidence=90.0, confidence_label=ConfidenceLabel.HIGH)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _alignment_result(score=70.0):
    return SimpleNamespace(final_score=score)


def _make_participant(session, code: str) -> Participant:
    participant = Participant(participant_code=code, enrollment_date=BASE_DATE, status="active")
    session.add(participant)
    session.flush()
    session.add(
        ParticipantProfile(
            participant_id=participant.id, chronotype_category="Intermediate",
            intrinsic_dlmo_time=hour_to_clock_time(21.0), adapted_dlmo_time=hour_to_clock_time(21.0),
            current_dlmo_time=hour_to_clock_time(21.0),
        )
    )
    session.commit()
    return participant


def _write_history(session, participant_id, start_date, hours, alignment_scores=None, compliance_values=None):
    n = len(hours)
    alignment_scores = alignment_scores or [70.0] * n
    for i, h in enumerate(hours):
        d = start_date + timedelta(days=i)
        if h is not None:
            label = CircadianLabel(
                participant_id=participant_id, target_date=d, is_latest=True, prediction_status="success",
                fused_dlmo_time=hour_to_clock_time(h), data_completeness=1.0,
            )
            session.add(label)
            session.flush()
            session.add(
                AlignmentResult(
                    circadian_label_id=label.id, participant_id=participant_id, target_date=d,
                    final_alignment_score=alignment_scores[i], phase_alignment_score=alignment_scores[i], behavioral_alignment_score=alignment_scores[i],
                )
            )
        if compliance_values is not None and compliance_values[i] is not None:
            rec = session.execute(select(Recommendation).limit(1)).scalars().first()
            if rec is None:
                rec = Recommendation(intervention_code="SAFETY_TEST_REC", intervention_type="screen", title="Test", literature_expected_improvement_minutes=15.0)
                session.add(rec)
                session.flush()
            session.add(
                InterventionLog(
                    participant_id=participant_id, recommendation_id=rec.id, log_date=d,
                    compliance_degree=compliance_values[i], compliance_binary=compliance_values[i] >= 0.65,
                )
            )
    session.commit()


def _open_flags(session, participant_id):
    return session.execute(
        select(SafetyFlag).where(SafetyFlag.participant_id == participant_id, SafetyFlag.resolved_date.is_(None))
    ).scalars().all()


# --- Scenario 1: high confidence, ordinary pattern -> normal prediction + recommendation ---


def test_scenario_1_high_confidence_ordinary_pattern(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-001")
    _write_history(session, participant.id, BASE_DATE, [21.0] * 14, compliance_values=[0.5] * 14)

    engine = SafetyEngine()
    output = engine.evaluate(
        session, participant.id, BASE_DATE + timedelta(days=14), _fusion_result(),
        _alignment_result(70.0), RecommendationInput("screen", "Try stopping screens by 10:00 PM."),
    )

    assert output.prediction_available is True
    assert output.status == STATUS_OK
    assert output.recommendation_available is True
    assert output.recommendation_suppressed is False
    report = run_sanity_checks(output)
    assert report.ok, report.summary_lines()


# --- Scenario 2/3/4: confidence tiers ---


def test_scenario_2_moderate_confidence(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-002")
    engine = SafetyEngine()
    output = engine.evaluate(
        session, participant.id, BASE_DATE, _fusion_result(final_confidence=70.0, confidence_label=ConfidenceLabel.MODERATE),
    )
    assert output.prediction_available is True
    assert output.display_precision == "NORMAL_WITH_QUALIFIER"
    assert output.qualifier_message is not None


def test_scenario_3_low_confidence(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-003")
    engine = SafetyEngine()
    output = engine.evaluate(
        session, participant.id, BASE_DATE, _fusion_result(final_confidence=50.0, confidence_label=ConfidenceLabel.LOW),
    )
    assert output.display_precision == "APPROXIMATE"
    assert output.dlmo_hour is not None


def test_scenario_4_no_prediction(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-004")
    engine = SafetyEngine()
    output = engine.evaluate(
        session, participant.id, BASE_DATE,
        _fusion_result(prediction_made=False, fused_final=None, final_confidence=20.0, confidence_label=ConfidenceLabel.NO_PREDICTION),
    )
    assert output.prediction_available is False
    assert output.dlmo_hour is None
    assert output.status == STATUS_INSUFFICIENT_DATA


# --- Scenario 5: persistent late phase -> moderate flag ---


def test_scenario_5_persistent_late_phase(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-005")
    _write_history(session, participant.id, BASE_DATE, [3.0] * 14)

    engine = SafetyEngine()
    output = engine.evaluate(session, participant.id, BASE_DATE + timedelta(days=14), _fusion_result())

    flag_types = [f.flag_type for f in output.active_safety_flags]
    assert "persistent_late_phase" in flag_types
    assert output.highest_safety_severity == MODERATE
    assert output.recommendation_suppressed is False


# --- Scenario 6: low alignment + high compliance -> moderate flag ---


def test_scenario_6_low_alignment_despite_compliance(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-006")
    _write_history(session, participant.id, BASE_DATE, [21.0] * 14, alignment_scores=[30.0] * 14, compliance_values=[0.85] * 14)

    engine = SafetyEngine()
    output = engine.evaluate(session, participant.id, BASE_DATE + timedelta(days=14), _fusion_result())

    flag_types = [f.flag_type for f in output.active_safety_flags]
    assert "low_alignment_despite_compliance" in flag_types
    assert output.highest_safety_severity == MODERATE


# --- Scenario 7: continuous DLMO drift -> high flag + suppression ---


def test_scenario_7_continuous_drift_suppresses_recommendation(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-007")
    hours = [(20.0 + i * (25.0 / 60.0)) % 24.0 for i in range(14)]
    _write_history(session, participant.id, BASE_DATE, hours)

    engine = SafetyEngine()
    output = engine.evaluate(
        session, participant.id, BASE_DATE + timedelta(days=14), _fusion_result(),
        recommendation=RecommendationInput("screen", "Try stopping screens by 10:00 PM."),
    )

    assert "continuous_dlmo_drift" in [f.flag_type for f in output.active_safety_flags]
    assert output.highest_safety_severity == HIGH
    assert output.recommendation_suppressed is True
    assert output.recommendation_available is False
    assert "healthcare professional" in output.recommendation_text


# --- Scenario 8: persistent early phase -> moderate flag ---


def test_scenario_8_persistent_early_phase(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-008")
    _write_history(session, participant.id, BASE_DATE, [18.5] * 14)

    engine = SafetyEngine()
    output = engine.evaluate(session, participant.id, BASE_DATE + timedelta(days=14), _fusion_result())

    assert "persistent_early_phase" in [f.flag_type for f in output.active_safety_flags]
    assert output.highest_safety_severity == MODERATE


# --- Scenario 9: multiple flags -> all retained, highest severity selected ---


def test_scenario_9_multiple_flags_retained_with_highest_severity(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-009")
    # Persistently late AND low-alignment-despite-compliance simultaneously.
    _write_history(session, participant.id, BASE_DATE, [3.0] * 14, alignment_scores=[30.0] * 14, compliance_values=[0.85] * 14)

    engine = SafetyEngine()
    output = engine.evaluate(session, participant.id, BASE_DATE + timedelta(days=14), _fusion_result())

    flag_types = {f.flag_type for f in output.active_safety_flags}
    assert "persistent_late_phase" in flag_types
    assert "low_alignment_despite_compliance" in flag_types
    assert output.highest_safety_severity == MODERATE  # neither is HIGH


# --- Scenario 10: flag resolves after normalization ---


def test_scenario_10_flag_resolves_after_sustained_normal_pattern(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-010")
    _write_history(session, participant.id, BASE_DATE, [3.0] * 14)  # triggers persistent_late_phase

    engine = SafetyEngine()
    first = engine.evaluate(session, participant.id, BASE_DATE + timedelta(days=14), _fusion_result())
    assert "persistent_late_phase" in [f.flag_type for f in first.active_safety_flags]

    # Now extend with enough normal days to satisfy the resolution
    # hysteresis (resolution_min_normal_observations = 7 by default),
    # keeping total rolling-window history at normal values only.
    normal_start = BASE_DATE + timedelta(days=14)
    _write_history(session, participant.id, normal_start, [21.0] * 14)

    second = engine.evaluate(session, participant.id, normal_start + timedelta(days=14), _fusion_result())
    assert "persistent_late_phase" not in [f.flag_type for f in second.active_safety_flags]

    resolved_rows = session.execute(
        select(SafetyFlag).where(SafetyFlag.participant_id == participant.id, SafetyFlag.flag_type == "persistent_late_phase")
    ).scalars().all()
    assert any(r.resolved_date is not None for r in resolved_rows)


# --- Scenario 11: invalid medical recommendation reaches safety layer -> blocked ---


def test_scenario_11_invalid_recommendation_blocked(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-011")
    _write_history(session, participant.id, BASE_DATE, [21.0] * 14, compliance_values=[0.5] * 14)

    engine = SafetyEngine()
    output = engine.evaluate(
        session, participant.id, BASE_DATE + timedelta(days=14), _fusion_result(),
        recommendation=RecommendationInput("medication", "Take melatonin at 9 PM."),
    )

    assert output.recommendation_available is False
    assert output.recommendation_text is None


# --- Scenario 12: midnight-crossing trajectory -> no false drift flag ---


def test_scenario_12_midnight_crossing_no_false_drift(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-012")
    hours = [23.9167 if i % 2 == 0 else 0.0833 for i in range(14)]  # oscillates but stable
    _write_history(session, participant.id, BASE_DATE, hours)

    engine = SafetyEngine()
    output = engine.evaluate(session, participant.id, BASE_DATE + timedelta(days=14), _fusion_result())

    assert "continuous_dlmo_drift" not in [f.flag_type for f in output.active_safety_flags]


# --- 25, 26. Database persistence / audit trail ---


def test_safety_flag_persisted_with_audit_fields(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-013")
    _write_history(session, participant.id, BASE_DATE, [3.0] * 14)

    engine = SafetyEngine()
    engine.evaluate(session, participant.id, BASE_DATE + timedelta(days=14), _fusion_result())

    row = session.execute(
        select(SafetyFlag).where(SafetyFlag.participant_id == participant.id, SafetyFlag.flag_type == "persistent_late_phase")
    ).scalars().one()
    assert row.severity == MODERATE
    assert row.message_key == "MESSAGE_PERSISTENT_LATE_PHASE"
    assert row.detection_version == DEFAULT_SAFETY_CONFIG.safety_config_version
    assert row.first_detected_date == BASE_DATE + timedelta(days=14)
    assert row.triggering_statistics is not None


def test_circadian_label_carries_safety_metadata(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-014")
    hours = [(20.0 + i * (25.0 / 60.0)) % 24.0 for i in range(14)]
    _write_history(session, participant.id, BASE_DATE, hours)
    today = BASE_DATE + timedelta(days=14)
    session.add(
        CircadianLabel(participant_id=participant.id, target_date=today, is_latest=True, prediction_status="success", fused_dlmo_time=hour_to_clock_time(21.75))
    )
    session.commit()

    engine = SafetyEngine()
    engine.evaluate(session, participant.id, today, _fusion_result())

    label = session.execute(
        select(CircadianLabel).where(CircadianLabel.participant_id == participant.id, CircadianLabel.target_date == today, CircadianLabel.is_latest.is_(True))
    ).scalars().one()
    assert label.safety_severity == HIGH
    assert label.recommendation_suppressed is True
    assert label.safe_output_status == STATUS_FLAGGED


# --- Property / invariant tests ---


def test_property_no_output_ever_contains_prohibited_language(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-015")
    hours = [(20.0 + i * (25.0 / 60.0)) % 24.0 for i in range(14)]
    _write_history(session, participant.id, BASE_DATE, hours)

    engine = SafetyEngine()
    output = engine.evaluate(
        session, participant.id, BASE_DATE + timedelta(days=14), _fusion_result(),
        recommendation=RecommendationInput("screen", "Try stopping screens by 10:00 PM."),
    )
    found = scan_for_prohibited_language(
        output.boundary_note, output.recommendation_text, output.non_diagnostic_statement, output.qualifier_message,
        *[f.message for f in output.active_safety_flags],
    )
    assert found == []


def test_property_safety_never_modifies_fused_dlmo(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-016")
    _write_history(session, participant.id, BASE_DATE, [3.0] * 14)
    fusion = _fusion_result(fused_final=21.6666)

    engine = SafetyEngine()
    output = engine.evaluate(session, participant.id, BASE_DATE + timedelta(days=14), fusion)

    assert output.dlmo_hour == pytest.approx(21.6666)
    assert fusion.fused_final == pytest.approx(21.6666)  # untouched


def test_property_moderate_does_not_suppress(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "SAFE-017")
    _write_history(session, participant.id, BASE_DATE, [3.0] * 14)

    engine = SafetyEngine()
    output = engine.evaluate(
        session, participant.id, BASE_DATE + timedelta(days=14), _fusion_result(),
        recommendation=RecommendationInput("screen", "Try stopping screens by 10:00 PM."),
    )
    assert output.highest_safety_severity == MODERATE
    assert output.recommendation_suppressed is False
    assert output.recommendation_available is True

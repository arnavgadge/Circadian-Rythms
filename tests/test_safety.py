"""Pure-logic tests for the Phase 14 safety + confidence layer (no
database) -- DB-integration / scenario tests live in
``test_safety_db.py``.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.fusion.config import ConfidenceLabel
from app.safety.catalogue_guard import validate_recommendation_safety
from app.safety.circular_stats import compute_circular_trend_minutes_per_day, signed_offset_from_midnight, unwrap_circular_series
from app.safety.config import DEFAULT_SAFETY_CONFIG, SafetyConfig
from app.safety.confidence_gate import apply_confidence_gate
from app.safety.enums import (
    APPROXIMATE, CONTINUOUS_DLMO_DRIFT, DETECTED, HIGH, LOW_ALIGNMENT_DESPITE_COMPLIANCE, MODERATE,
    NONE_, NORMAL, NORMAL_WITH_QUALIFIER, PERSISTENT_EARLY_PHASE, PERSISTENT_LATE_PHASE, PERSISTING, RESOLVED,
)
from app.safety.guardrails import scan_for_prohibited_language
from app.safety.lifecycle import determine_severity, reconcile_flag
from app.safety.messages import BOUNDARY_NOTE_SHORT, PROHIBITED_PHRASES
from app.safety.patterns import (
    DayRecord,
    detect_continuous_drift,
    detect_low_alignment_despite_compliance,
    detect_persistent_early_phase,
    detect_persistent_late_phase,
)

BASE_DATE = date(2026, 4, 1)


def _fusion_result(**overrides):
    defaults = dict(prediction_made=True, fused_final=21.75, final_confidence=90.0, confidence_label=ConfidenceLabel.HIGH)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# --- 1. Confidence threshold boundaries / 2, 3, 4, 5 ---


def test_high_confidence_output():
    gate = apply_confidence_gate(_fusion_result(final_confidence=85.0, confidence_label=ConfidenceLabel.HIGH))
    assert gate.prediction_available is True
    assert gate.display_precision == NORMAL


def test_moderate_confidence_output():
    gate = apply_confidence_gate(_fusion_result(final_confidence=70.0, confidence_label=ConfidenceLabel.MODERATE))
    assert gate.display_precision == NORMAL_WITH_QUALIFIER
    assert gate.prediction_available is True


def test_low_confidence_output():
    gate = apply_confidence_gate(_fusion_result(final_confidence=50.0, confidence_label=ConfidenceLabel.LOW))
    assert gate.display_precision == APPROXIMATE
    assert gate.prediction_available is True


def test_no_prediction_state():
    gate = apply_confidence_gate(_fusion_result(prediction_made=False, fused_final=None, final_confidence=20.0, confidence_label=ConfidenceLabel.NO_PREDICTION))
    assert gate.prediction_available is False
    assert gate.display_precision == NONE_


def test_confidence_below_40_cannot_produce_normal_prediction():
    gate = apply_confidence_gate(_fusion_result(prediction_made=False, fused_final=None, final_confidence=39.9, confidence_label=ConfidenceLabel.NO_PREDICTION))
    assert gate.prediction_available is False


# --- 6, 7. Tier-1 missing / incomplete window (already enforced upstream by fusion.prediction_made) ---


def test_gate_never_overrides_fusion_prediction_made_false():
    # Even a suspiciously high confidence number must not leak a
    # prediction through if fusion itself decided not to predict.
    gate = apply_confidence_gate(_fusion_result(prediction_made=False, fused_final=None, final_confidence=99.0, confidence_label=ConfidenceLabel.HIGH))
    assert gate.prediction_available is False


def test_gate_never_overrides_missing_fused_value():
    gate = apply_confidence_gate(_fusion_result(prediction_made=True, fused_final=None, final_confidence=90.0, confidence_label=ConfidenceLabel.HIGH))
    assert gate.prediction_available is False


# --- 13, 14, 15. Circular mean / trend / midnight crossing ---


def test_unwrap_circular_series_handles_midnight_crossing():
    unwrapped = unwrap_circular_series([23.8333, 0.0833, 0.3333])  # 23:50, 00:05, 00:20
    assert unwrapped[1] > unwrapped[0]
    assert unwrapped[2] > unwrapped[1]
    assert unwrapped[2] - unwrapped[0] == pytest.approx(0.5, abs=0.01)  # 30 minutes total drift


def test_circular_trend_recovers_known_drift_across_midnight():
    dated_hours = [
        (BASE_DATE + timedelta(days=i), (23.0 + i * (20.0 / 60.0)) % 24.0) for i in range(10)
    ]  # ~20 min/day later, crossing midnight partway through
    trend = compute_circular_trend_minutes_per_day(dated_hours)
    assert trend == pytest.approx(20.0, abs=1.0)


def test_circular_trend_near_zero_for_stable_midnight_oscillation():
    # Alternates just before/after midnight but with no real drift.
    dated_hours = [(BASE_DATE + timedelta(days=i), 23.9167 if i % 2 == 0 else 0.0833) for i in range(12)]
    trend = compute_circular_trend_minutes_per_day(dated_hours)
    assert abs(trend) < 5.0


def test_signed_offset_from_midnight_is_monotonic_across_dlmo_range():
    values = [18.0, 20.0, 22.0, 23.9, 0.0, 1.0, 3.0, 6.0]
    offsets = [signed_offset_from_midnight(v) for v in values]
    assert offsets == sorted(offsets)  # strictly increasing through the realistic DLMO arc


# --- 8. Persistent late detection ---


def _records(hours, alignment=70.0, compliance=None, available=True, start=BASE_DATE):
    return [
        DayRecord(start + timedelta(days=i), available, h, alignment, compliance)
        for i, h in enumerate(hours)
    ]


def test_persistent_late_phase_triggers_when_mean_later_than_threshold():
    records = _records([3.0] * 12)  # 3:00 AM, well past the 2:00 AM threshold
    result = detect_persistent_late_phase(records)
    assert result.triggering is True


def test_persistent_late_phase_does_not_trigger_for_normal_hours():
    records = _records([21.5] * 12)  # 9:30 PM
    result = detect_persistent_late_phase(records)
    assert result.triggering is False


# --- 9. Persistent early detection ---


def test_persistent_early_phase_triggers_for_consistently_early_dlmo():
    records = _records([18.5] * 12)  # 6:30 PM
    result = detect_persistent_early_phase(records)
    assert result.triggering is True


def test_persistent_early_phase_does_not_trigger_just_after_threshold():
    records = _records([20.0] * 12)  # 8:00 PM -- later than the 7:30 PM threshold
    result = detect_persistent_early_phase(records)
    assert result.triggering is False


# --- 10. Continuous drift detection ---


def test_continuous_drift_triggers_for_steady_large_shift():
    hours = [(21.0 + i * (25.0 / 60.0)) % 24.0 for i in range(12)]
    records = _records(hours)
    result = detect_continuous_drift(records)
    assert result.triggering is True


def test_continuous_drift_does_not_trigger_for_stable_pattern():
    records = _records([21.0, 21.1, 20.9, 21.05, 20.95, 21.0, 21.1, 20.9, 21.0, 21.0, 21.05, 20.95])
    result = detect_continuous_drift(records)
    assert result.triggering is False


# --- 11. Low alignment despite compliance ---


def test_low_alignment_despite_compliance_triggers():
    records = [DayRecord(BASE_DATE + timedelta(days=i), True, 21.0, 30.0, 0.85) for i in range(12)]
    result = detect_low_alignment_despite_compliance(records)
    assert result.triggering is True


def test_low_alignment_without_high_compliance_does_not_trigger():
    records = [DayRecord(BASE_DATE + timedelta(days=i), True, 21.0, 30.0, 0.2) for i in range(12)]
    result = detect_low_alignment_despite_compliance(records)
    assert result.triggering is False


# --- 12. Minimum observation count ---


def test_no_flag_from_too_few_observations():
    records = _records([3.0, 3.1])  # only 2 days, far below the 10-observation minimum
    result = detect_persistent_late_phase(records)
    assert result.triggering is False
    assert "insufficient_observations" in result.triggering_statistics.get("reason", "")


def test_unavailable_days_are_not_counted_as_evidence():
    available = _records([3.0] * 10)
    unavailable = [DayRecord(BASE_DATE + timedelta(days=100 + i), False, None, None, None) for i in range(20)]
    result = detect_persistent_late_phase(available + unavailable)
    # Still triggers on the 10 real observations; the 20 unavailable
    # days must not dilute or block it, nor count toward the minimum.
    assert result.triggering is True
    assert result.n_observations == 10


# --- 16, 17. Multiple flags / severity ordering ---


def test_determine_severity_only_drift_is_high():
    assert determine_severity(CONTINUOUS_DLMO_DRIFT) == HIGH
    assert determine_severity(PERSISTENT_LATE_PHASE) == MODERATE
    assert determine_severity(PERSISTENT_EARLY_PHASE) == MODERATE
    assert determine_severity(LOW_ALIGNMENT_DESPITE_COMPLIANCE) == MODERATE


# --- Flag lifecycle reconciliation ---


def test_reconcile_flag_detected_when_new():
    from app.safety.patterns import PatternDetectionResult

    detection = PatternDetectionResult(PERSISTENT_LATE_PHASE, True, 12, {})
    decision = reconcile_flag(detection, has_existing_open_flag=False)
    assert decision.lifecycle_state == DETECTED


def test_reconcile_flag_persisting_when_still_triggering_and_open():
    from app.safety.patterns import PatternDetectionResult

    detection = PatternDetectionResult(PERSISTENT_LATE_PHASE, True, 12, {})
    decision = reconcile_flag(detection, has_existing_open_flag=True)
    assert decision.lifecycle_state == PERSISTING


def test_reconcile_flag_not_resolved_from_single_normal_window_without_confirmation():
    from app.safety.patterns import PatternDetectionResult

    detection = PatternDetectionResult(PERSISTENT_LATE_PHASE, False, 12, {})
    resolution_check_still_triggering = PatternDetectionResult(PERSISTENT_LATE_PHASE, True, 7, {})
    decision = reconcile_flag(detection, has_existing_open_flag=True, resolution_check=resolution_check_still_triggering)
    assert decision.lifecycle_state == PERSISTING  # hysteresis: not yet resolved


def test_reconcile_flag_resolved_after_sustained_normal_window():
    from app.safety.patterns import PatternDetectionResult

    detection = PatternDetectionResult(PERSISTENT_LATE_PHASE, False, 12, {})
    resolution_check_normal = PatternDetectionResult(PERSISTENT_LATE_PHASE, False, 7, {})
    decision = reconcile_flag(detection, has_existing_open_flag=True, resolution_check=resolution_check_normal)
    assert decision.lifecycle_state == RESOLVED


def test_reconcile_flag_none_when_never_triggered_and_no_open_flag():
    from app.safety.patterns import PatternDetectionResult

    detection = PatternDetectionResult(PERSISTENT_LATE_PHASE, False, 12, {})
    decision = reconcile_flag(detection, has_existing_open_flag=False)
    assert decision is None


# --- 21, 22. Invalid recommendation blocking / safe catalogue validation ---


def test_valid_catalogue_recommendation_passes():
    result = validate_recommendation_safety("screen", "Try stopping screens by 10:00 PM.")
    assert result.is_safe is True


def test_unapproved_intervention_type_is_blocked():
    result = validate_recommendation_safety("medication", "Take this at bedtime.")
    assert result.is_safe is False


def test_medical_language_is_blocked_even_for_an_approved_type():
    result = validate_recommendation_safety("screen", "Take melatonin 30 minutes before your screen cutoff.")
    assert result.is_safe is False
    assert "melatonin" in result.reason


def test_none_intervention_type_is_blocked():
    result = validate_recommendation_safety(None, "Some text")
    assert result.is_safe is False


# --- 23, 24. Boundary-message availability / prohibited-language safeguards ---


def test_boundary_note_is_the_locked_exact_string():
    assert BOUNDARY_NOTE_SHORT == "Estimated from behavioral patterns. Not a clinical measurement."


def test_scan_detects_each_prohibited_phrase():
    for phrase in PROHIBITED_PHRASES:
        found = scan_for_prohibited_language(f"Some output containing: {phrase}")
        assert phrase in found


def test_scan_does_not_false_positive_on_legitimate_disclaimer():
    from app.safety.messages import NON_DIAGNOSTIC_STATEMENT

    assert scan_for_prohibited_language(NON_DIAGNOSTIC_STATEMENT) == []


# --- 27. Deterministic evaluation ---


def test_detectors_are_deterministic():
    records = _records([3.0] * 12)
    result_a = detect_persistent_late_phase(records)
    result_b = detect_persistent_late_phase(records)
    assert result_a == result_b

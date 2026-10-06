"""AUDIT 16 -- Confidence gating.

Verifies:
1. The exact Q25 confidence-label boundary comparisons (>=80 HIGH,
   60<=x<80 MODERATE, 40<=x<60 LOW, <40 NO_PREDICTION) at all six
   documented boundary values.
2. Each documented no-prediction trigger path in isolation:
   (a) confidence score < 40, (b) Tier-1 critical data unavailable,
   (c) window completeness below the configured threshold (0.5 / 50%,
   confirmed by reading app.fusion.config.DEFAULT_FUSION_CONFIG).
3. End-to-end propagation of the LOW-confidence "approximate" flag
   through app.safety.confidence_gate -> app.safety.engine.SafetyEngine
   (implicitly, via the same gate) -> app.api.services.status_service
   -> the final StatusResponse.approximate / StatusResponse.confidence.approximate
   fields.
"""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from app.fusion.config import DEFAULT_FUSION_CONFIG, ConfidenceLabel
from app.fusion.confidence import DataQualityInput, confidence_label, should_suppress_prediction
from app.fusion.config import DataQualityTier
from app.fusion.fuse import fuse
from app.safety.confidence_gate import apply_confidence_gate
from app.safety.enums import APPROXIMATE, NONE_, NORMAL, NORMAL_WITH_QUALIFIER
from app.api.services.status_service import StatusService


# ---------------------------------------------------------------------------
# 1. Exact boundary comparisons.
# ---------------------------------------------------------------------------

BOUNDARY_CASES = [
    (80.0, ConfidenceLabel.HIGH),
    (79.999, ConfidenceLabel.MODERATE),
    (60.0, ConfidenceLabel.MODERATE),
    (59.999, ConfidenceLabel.LOW),
    (40.0, ConfidenceLabel.LOW),
    (39.999, ConfidenceLabel.NO_PREDICTION),
]


@pytest.mark.parametrize("score,expected", BOUNDARY_CASES)
def test_confidence_label_boundaries(score, expected):
    assert confidence_label(score) == expected


def test_confidence_label_thresholds_are_locked_q25_values():
    # Guard against silent drift of the underlying threshold tuple itself.
    assert DEFAULT_FUSION_CONFIG.confidence_label_thresholds == (80.0, 60.0, 40.0)


# ---------------------------------------------------------------------------
# 2. No-prediction trigger paths, isolated.
# ---------------------------------------------------------------------------

def test_completeness_threshold_is_point_five():
    # Report the real value in case it ever drifts from the doc's "50%".
    assert DEFAULT_FUSION_CONFIG.no_prediction_completeness_threshold == 0.5
    assert DEFAULT_FUSION_CONFIG.no_prediction_confidence_threshold == 40.0


def test_should_suppress_low_confidence_only():
    dq = DataQualityInput(tier=DataQualityTier.HIGH, window_completeness=1.0, tier1_signals_missing=False)
    assert should_suppress_prediction(dq, confidence=39.9) is True
    assert should_suppress_prediction(dq, confidence=40.0) is False


def test_should_suppress_tier1_missing_even_with_high_confidence():
    # High raw confidence score, but Tier-1 missing -- must still suppress.
    dq = DataQualityInput(tier=DataQualityTier.HIGH, window_completeness=1.0, tier1_signals_missing=True)
    assert should_suppress_prediction(dq, confidence=95.0) is True


def test_should_suppress_low_completeness_even_with_high_confidence():
    dq = DataQualityInput(tier=DataQualityTier.HIGH, window_completeness=0.49, tier1_signals_missing=False)
    assert should_suppress_prediction(dq, confidence=95.0) is True

    # At exactly the threshold (0.5) it must NOT trigger this path (< 0.5, not <=).
    dq_at_threshold = DataQualityInput(tier=DataQualityTier.HIGH, window_completeness=0.5, tier1_signals_missing=False)
    assert should_suppress_prediction(dq_at_threshold, confidence=95.0) is False


def test_should_suppress_none_when_all_conditions_clear():
    dq = DataQualityInput(tier=DataQualityTier.HIGH, window_completeness=1.0, tier1_signals_missing=False)
    assert should_suppress_prediction(dq, confidence=95.0) is False


def test_fuse_suppresses_via_tier1_missing_despite_agreeing_estimators():
    # Two estimators in close agreement (-> NORMAL regime, no confidence
    # penalty) would otherwise yield a high final confidence; tier1_signals_missing
    # must still force prediction_made=False.
    dq = DataQualityInput(tier=DataQualityTier.HIGH, window_completeness=1.0, tier1_signals_missing=True)
    result = fuse(xgb_dlmo=21.0, state_dlmo=21.05, previous_fused_dlmo=None, data_quality=dq)
    assert result.final_confidence >= 80.0  # confidence math itself is untouched
    assert result.prediction_made is False


def test_fuse_suppresses_via_low_completeness_despite_high_confidence():
    dq = DataQualityInput(tier=DataQualityTier.HIGH, window_completeness=0.2, tier1_signals_missing=False)
    result = fuse(xgb_dlmo=21.0, state_dlmo=21.05, previous_fused_dlmo=None, data_quality=dq)
    assert result.final_confidence >= 80.0
    assert result.prediction_made is False


def test_fuse_suppresses_via_low_confidence_score():
    dq = DataQualityInput(tier=DataQualityTier.VERY_LOW, window_completeness=1.0, tier1_signals_missing=False)
    # VERY_LOW base confidence is 20.0, extreme disagreement drives it down further.
    result = fuse(xgb_dlmo=8.0, state_dlmo=20.0, previous_fused_dlmo=None, data_quality=dq)
    assert result.final_confidence < 40.0
    assert result.prediction_made is False
    assert result.confidence_label == ConfidenceLabel.NO_PREDICTION


# ---------------------------------------------------------------------------
# 3. Approximate-flag propagation, end to end.
# ---------------------------------------------------------------------------

def _low_confidence_fusion_result():
    dq = DataQualityInput(tier=DataQualityTier.MODERATE, window_completeness=1.0, tier1_signals_missing=False, base_confidence=45.0)
    return fuse(xgb_dlmo=21.0, state_dlmo=21.1, previous_fused_dlmo=None, data_quality=dq)


def test_low_confidence_fusion_result_yields_low_label():
    result = _low_confidence_fusion_result()
    assert result.confidence_label == ConfidenceLabel.LOW
    assert result.is_approximate is True
    assert result.prediction_made is True


def test_confidence_gate_maps_low_to_approximate_precision():
    result = _low_confidence_fusion_result()
    gate = apply_confidence_gate(result)
    assert gate.prediction_available is True
    assert gate.confidence_label == "low"
    assert gate.display_precision == APPROXIMATE


def test_confidence_gate_display_precision_matrix():
    # Cross-check every label maps to the documented precision, via a
    # minimal fake fusion_result exposing just the attributes the gate reads.
    def fake(label, made=True, final=21.0):
        return SimpleNamespace(prediction_made=made, fused_final=final, final_confidence=50.0, confidence_label=label)

    assert apply_confidence_gate(fake(ConfidenceLabel.HIGH)).display_precision == NORMAL
    assert apply_confidence_gate(fake(ConfidenceLabel.MODERATE)).display_precision == NORMAL_WITH_QUALIFIER
    assert apply_confidence_gate(fake(ConfidenceLabel.LOW)).display_precision == APPROXIMATE
    assert apply_confidence_gate(fake(ConfidenceLabel.NO_PREDICTION)).display_precision == NONE_
    assert apply_confidence_gate(fake(ConfidenceLabel.HIGH, made=False)).display_precision == NONE_


class _FakeParticipantRepository:
    def get(self, participant_id):
        return SimpleNamespace(id=participant_id)

    def get_profile(self, participant_id):
        return None


class _FakeCircadianRepository:
    def __init__(self, label):
        self._label = label

    def get_for_date(self, participant_id, target_date):
        return self._label

    def get_latest(self, participant_id):
        return self._label

    def get_contributors(self, label_id):
        return []


class _FakeInterventionRepository:
    def get_history(self, participant_id, start, end, *_args, **_kwargs):
        return []

    def get_recommendation(self, recommendation_id):
        return None


class _FakeSafetyRepository:
    def get_active_flags(self, participant_id):
        return []


def _build_status_service(label):
    return StatusService(
        participant_repository=_FakeParticipantRepository(),
        circadian_repository=_FakeCircadianRepository(label),
        intervention_repository=_FakeInterventionRepository(),
        safety_repository=_FakeSafetyRepository(),
    )


def test_status_service_propagates_low_confidence_approximate_flag():
    """Isolates the LOW-confidence path through status_service.py: a
    persisted daily label with confidence_label='low' must produce a
    StatusResponse with approximate=True in both the top-level field
    and confidence.approximate."""

    label = SimpleNamespace(
        id=1,
        fused_dlmo_time=datetime.time(21, 30),
        confidence_label="low",
        confidence_score=45.0,
        alignment_result=None,
        target_date=datetime.date(2026, 9, 9),
        safety_severity=None,
        recommendation_suppressed=None,
    )
    service = _build_status_service(label)
    response = service.build_status(participant_id=1)

    assert response.prediction_available is True
    assert response.approximate is True
    assert response.confidence.approximate is True
    assert response.confidence.label == "low"


def test_status_service_high_confidence_is_not_approximate():
    label = SimpleNamespace(
        id=1,
        fused_dlmo_time=datetime.time(21, 30),
        confidence_label="high",
        confidence_score=90.0,
        alignment_result=None,
        target_date=datetime.date(2026, 9, 9),
        safety_severity=None,
        recommendation_suppressed=None,
    )
    service = _build_status_service(label)
    response = service.build_status(participant_id=1)

    assert response.approximate is False
    assert response.confidence.approximate is False

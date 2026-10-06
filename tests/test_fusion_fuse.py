"""Tests for the top-level fuse() orchestration: end-to-end scenarios,
model-availability fallback, numerical robustness, and determinism.
"""

from __future__ import annotations

import math

import pytest

from app.fusion.config import ConfidenceLabel, DataQualityTier, DisagreementRegime
from app.fusion.confidence import DataQualityInput
from app.fusion.fuse import fuse


def _hm(hour: int, minute: int) -> float:
    return hour + minute / 60.0


def _dq(tier=DataQualityTier.HIGH, completeness=1.0, tier1_missing=False, base_confidence=None):
    return DataQualityInput(
        tier=tier, window_completeness=completeness, tier1_signals_missing=tier1_missing, base_confidence=base_confidence
    )


# --- Worked example: 23:50 / 00:10, normal disagreement, stays near midnight ---

def test_worked_example_23_50_and_00_10_stays_near_midnight():
    result = fuse(_hm(23, 50), _hm(0, 10), previous_fused_dlmo=None, data_quality=_dq())
    assert result.disagreement_regime == DisagreementRegime.NORMAL
    assert result.prediction_made is True
    hour = result.fused_final
    # near midnight: either just before 24 or just after 0
    assert hour > 23.5 or hour < 0.5


def test_worked_example_reversed_order():
    result = fuse(_hm(0, 10), _hm(23, 50), previous_fused_dlmo=None, data_quality=_dq())
    hour = result.fused_final
    assert hour > 23.5 or hour < 0.5


# --- Large disagreement + continuity limiting ---

def test_large_disagreement_triggers_continuity_limiting_against_previous_fused():
    # previous fused DLMO is far from both new estimates -> expect the
    # continuity cap to visibly constrain movement.
    result = fuse(2.0, 3.0, previous_fused_dlmo=_hm(23, 50), data_quality=_dq())
    # Whatever the raw fused value, the final must be within that
    # regime's cap of the previous fused value.
    from app.synthetic.time_utils import circular_diff_hours

    actual_move = abs(circular_diff_hours(result.fused_final, _hm(23, 50))) * 60.0
    assert actual_move <= result.continuity_cap_minutes + 1e-6


# --- Previous-DLMO continuity anchor ---

def test_continuity_anchor_is_previous_fused_not_state_or_xgb():
    # If continuity used the state or xgb estimate as the anchor instead
    # of previous_fused_dlmo, the cap would not bind here (state and xgb
    # are close to each other but previous_fused is far from both).
    result = fuse(10.0, 10.1, previous_fused_dlmo=4.0, data_quality=_dq())
    assert result.continuity_applied is True


# --- 23. XGB unavailable fallback ---

def test_xgb_unavailable_state_becomes_full_weight():
    result = fuse(None, 10.0, previous_fused_dlmo=None, data_quality=_dq())
    assert result.xgb_available is False
    assert result.state_available is True
    assert result.xgb_final_weight == pytest.approx(0.0)
    assert result.state_final_weight == pytest.approx(1.0)
    assert result.fused_final == pytest.approx(10.0, abs=1e-6)
    assert result.disagreement_minutes is None
    assert result.disagreement_regime is None


def test_xgb_unavailable_reduces_confidence():
    result = fuse(None, 10.0, previous_fused_dlmo=None, data_quality=_dq(base_confidence=90.0))
    assert result.final_confidence < 90.0


# --- 24. State unavailable fallback ---

def test_state_unavailable_xgb_becomes_fallback():
    result = fuse(14.0, None, previous_fused_dlmo=None, data_quality=_dq())
    assert result.xgb_available is True
    assert result.state_available is False
    assert result.xgb_final_weight == pytest.approx(1.0)
    assert result.state_final_weight == pytest.approx(0.0)
    assert result.fused_final == pytest.approx(14.0, abs=1e-6)


# --- 25. Both unavailable ---

def test_both_unavailable_produces_no_prediction():
    result = fuse(None, None, previous_fused_dlmo=None, data_quality=_dq())
    assert result.prediction_made is False
    assert result.fused_final is None
    assert result.xgb_available is False
    assert result.state_available is False


def test_both_unavailable_falls_back_to_previous_fused_for_diagnostics():
    result = fuse(None, None, previous_fused_dlmo=15.5, data_quality=_dq())
    assert result.prediction_made is False
    assert result.fused_final == pytest.approx(15.5)
    assert result.used_fallback is True


# --- 26. NaN handling ---

def test_nan_xgb_treated_as_unavailable():
    result = fuse(float("nan"), 10.0, previous_fused_dlmo=None, data_quality=_dq())
    assert result.xgb_available is False
    assert result.fused_final == pytest.approx(10.0, abs=1e-6)


def test_nan_both_produces_no_prediction():
    result = fuse(float("nan"), float("nan"), previous_fused_dlmo=None, data_quality=_dq())
    assert result.prediction_made is False


# --- 27. Infinity handling ---

def test_infinity_state_treated_as_unavailable():
    result = fuse(14.0, float("inf"), previous_fused_dlmo=None, data_quality=_dq())
    assert result.state_available is False
    assert result.fused_final == pytest.approx(14.0, abs=1e-6)


def test_negative_infinity_treated_as_unavailable():
    result = fuse(float("-inf"), 10.0, previous_fused_dlmo=None, data_quality=_dq())
    assert result.xgb_available is False


# --- No-prediction end-to-end ---

def test_end_to_end_no_prediction_when_tier1_missing():
    result = fuse(14.0, 14.2, previous_fused_dlmo=None, data_quality=_dq(tier1_missing=True))
    assert result.prediction_made is False
    # A value is still computed for research/debugging transparency.
    assert result.fused_final is not None


def test_end_to_end_no_prediction_when_completeness_too_low():
    result = fuse(14.0, 14.2, previous_fused_dlmo=None, data_quality=_dq(completeness=0.3))
    assert result.prediction_made is False


def test_end_to_end_is_approximate_flag_for_low_confidence():
    result = fuse(14.0, 20.0, previous_fused_dlmo=None, data_quality=_dq(tier=DataQualityTier.VERY_LOW, base_confidence=45.0))
    if result.confidence_label == ConfidenceLabel.LOW:
        assert result.is_approximate is True


def test_high_confidence_is_not_approximate():
    result = fuse(14.0, 14.1, previous_fused_dlmo=None, data_quality=_dq(base_confidence=95.0))
    assert result.confidence_label == ConfidenceLabel.HIGH
    assert result.is_approximate is False


# --- 29. Deterministic fusion ---

def test_fuse_is_deterministic():
    args = (_hm(22, 15), _hm(23, 5), _hm(21, 50), _dq())
    result_a = fuse(*args)
    result_b = fuse(*args)
    assert result_a == result_b


def test_fuse_disagreement_minutes_matches_manual_circular_diff():
    from app.synthetic.time_utils import circular_diff_hours

    xgb, state = 10.0, 10.5
    result = fuse(xgb, state, None, _dq())
    expected = abs(circular_diff_hours(xgb, state)) * 60.0
    assert result.disagreement_minutes == pytest.approx(expected, abs=1e-6)


def test_diagnostic_fields_are_all_present_and_consistent():
    result = fuse(_hm(23, 50), _hm(0, 10), previous_fused_dlmo=_hm(23, 40), data_quality=_dq())
    assert result.xgb_base_weight + result.state_base_weight == pytest.approx(1.0)
    assert result.xgb_final_weight + result.state_final_weight == pytest.approx(1.0)
    assert 0.0 <= result.final_confidence <= 100.0
    assert isinstance(result.prediction_made, bool)

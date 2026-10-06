"""Tests for Layer 4: confidence penalties, labels, and the no-prediction rule."""

from __future__ import annotations

import pytest

from app.fusion.config import ConfidenceLabel, DataQualityTier, DisagreementRegime
from app.fusion.confidence import (
    DataQualityInput,
    apply_confidence_penalty,
    confidence_label,
    get_base_confidence,
    should_suppress_prediction,
)


# --- 17. Confidence penalties ---

@pytest.mark.parametrize(
    "regime, expected_penalty_applied",
    [
        (DisagreementRegime.NORMAL, 0.0),
        (DisagreementRegime.MODERATE, -8.0),
        (DisagreementRegime.LARGE, -18.0),
        (DisagreementRegime.EXTREME, -30.0),
    ],
)
def test_confidence_penalty_by_regime(regime, expected_penalty_applied):
    result = apply_confidence_penalty(90.0, regime)
    assert result == pytest.approx(90.0 + expected_penalty_applied)


def test_confidence_penalty_clamped_at_zero():
    result = apply_confidence_penalty(10.0, DisagreementRegime.EXTREME)
    assert result == pytest.approx(0.0)


def test_confidence_penalty_clamped_at_hundred():
    result = apply_confidence_penalty(150.0, DisagreementRegime.NORMAL)
    assert result == pytest.approx(100.0)


# --- 18. Confidence thresholds ---

@pytest.mark.parametrize(
    "score, expected",
    [
        (100.0, ConfidenceLabel.HIGH),
        (80.0, ConfidenceLabel.HIGH),
        (79.9, ConfidenceLabel.MODERATE),
        (60.0, ConfidenceLabel.MODERATE),
        (59.9, ConfidenceLabel.LOW),
        (40.0, ConfidenceLabel.LOW),
        (39.9, ConfidenceLabel.NO_PREDICTION),
        (0.0, ConfidenceLabel.NO_PREDICTION),
    ],
)
def test_confidence_label_thresholds(score, expected):
    assert confidence_label(score) == expected


# --- 19. Low-confidence approximate metadata ---

def test_low_label_is_the_approximate_display_band():
    assert confidence_label(45.0) == ConfidenceLabel.LOW  # >= 40, still shown, but approximate per fuse()


# --- 20, 21, 22. No-prediction conditions ---

def test_no_prediction_when_tier1_missing():
    dq = DataQualityInput(tier=DataQualityTier.HIGH, window_completeness=1.0, tier1_signals_missing=True)
    assert should_suppress_prediction(dq, confidence=95.0) is True


def test_no_prediction_when_completeness_below_50_percent():
    dq = DataQualityInput(tier=DataQualityTier.LOW, window_completeness=0.49, tier1_signals_missing=False)
    assert should_suppress_prediction(dq, confidence=95.0) is True


def test_prediction_allowed_at_exactly_50_percent_completeness():
    dq = DataQualityInput(tier=DataQualityTier.LOW, window_completeness=0.50, tier1_signals_missing=False)
    assert should_suppress_prediction(dq, confidence=95.0) is False


def test_no_prediction_when_confidence_below_40():
    dq = DataQualityInput(tier=DataQualityTier.HIGH, window_completeness=1.0, tier1_signals_missing=False)
    assert should_suppress_prediction(dq, confidence=39.9) is True


def test_prediction_allowed_when_all_conditions_pass():
    dq = DataQualityInput(tier=DataQualityTier.HIGH, window_completeness=1.0, tier1_signals_missing=False)
    assert should_suppress_prediction(dq, confidence=85.0) is False


def test_get_base_confidence_uses_override_when_given():
    dq = DataQualityInput(tier=DataQualityTier.LOW, window_completeness=1.0, base_confidence=77.0)
    assert get_base_confidence(dq) == pytest.approx(77.0)


def test_get_base_confidence_falls_back_to_tier_default():
    dq = DataQualityInput(tier=DataQualityTier.VERY_LOW, window_completeness=1.0)
    assert get_base_confidence(dq) == pytest.approx(20.0)

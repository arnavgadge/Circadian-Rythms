"""Tests for Layers 1-2: base weights and disagreement-based adjustment."""

from __future__ import annotations

import pytest

from app.fusion.config import DataQualityTier, DisagreementRegime
from app.fusion.weights import FusionWeights, adjust_weights, classify_disagreement, get_base_weights

# --- 1. Base weight selection ---

@pytest.mark.parametrize(
    "tier, expected_xgb, expected_state",
    [
        (DataQualityTier.HIGH, 0.65, 0.35),
        (DataQualityTier.MODERATE, 0.55, 0.45),
        (DataQualityTier.LOW, 0.40, 0.60),
        (DataQualityTier.VERY_LOW, 0.20, 0.80),
    ],
)
def test_base_weight_selection(tier, expected_xgb, expected_state):
    weights = get_base_weights(tier)
    assert weights.xgb == pytest.approx(expected_xgb)
    assert weights.state == pytest.approx(expected_state)


# --- 2. Weight normalization ---

def test_weights_must_sum_to_one():
    FusionWeights(xgb=0.65, state=0.35)  # must not raise
    with pytest.raises(ValueError):
        FusionWeights(xgb=0.7, state=0.4)


@pytest.mark.parametrize("tier", list(DataQualityTier))
def test_base_weights_are_normalized_for_every_tier(tier):
    weights = get_base_weights(tier)
    assert weights.xgb + weights.state == pytest.approx(1.0)


# --- 3. Disagreement classification ---

@pytest.mark.parametrize(
    "minutes, expected",
    [
        (0.0, DisagreementRegime.NORMAL),
        (10.0, DisagreementRegime.NORMAL),
        (25.0, DisagreementRegime.MODERATE),
        (40.0, DisagreementRegime.MODERATE),
        (50.0, DisagreementRegime.LARGE),
        (70.0, DisagreementRegime.LARGE),
        (100.0, DisagreementRegime.EXTREME),
        (500.0, DisagreementRegime.EXTREME),
    ],
)
def test_disagreement_classification(minutes, expected):
    assert classify_disagreement(minutes) == expected


def test_disagreement_classification_uses_absolute_value():
    assert classify_disagreement(-10.0) == DisagreementRegime.NORMAL
    assert classify_disagreement(-100.0) == DisagreementRegime.EXTREME


# --- 4, 5, 6. Exact boundary inclusivity ---

def test_exact_20_minute_boundary_is_normal():
    assert classify_disagreement(20.0) == DisagreementRegime.NORMAL


def test_exact_45_minute_boundary_is_moderate():
    assert classify_disagreement(45.0) == DisagreementRegime.MODERATE


def test_exact_75_minute_boundary_is_large():
    assert classify_disagreement(75.0) == DisagreementRegime.LARGE


def test_just_over_75_minutes_is_extreme():
    assert classify_disagreement(75.5) == DisagreementRegime.EXTREME


def test_boundary_survives_tiny_floating_point_noise():
    # Circular-arithmetic error can land a few ULPs over an intended
    # exact boundary; classification must not flip regimes because of it.
    assert classify_disagreement(20.000000000000142) == DisagreementRegime.NORMAL
    assert classify_disagreement(45.00000000000006) == DisagreementRegime.MODERATE


# --- 7, 8, 9. XGB weight reduction ---

def test_moderate_xgb_reduction():
    base = get_base_weights(DataQualityTier.HIGH)
    adjusted = adjust_weights(base, DisagreementRegime.MODERATE)
    assert adjusted.xgb == pytest.approx(0.55)
    assert adjusted.state == pytest.approx(0.45)


def test_large_xgb_reduction():
    base = get_base_weights(DataQualityTier.HIGH)
    adjusted = adjust_weights(base, DisagreementRegime.LARGE)
    assert adjusted.xgb == pytest.approx(0.45)
    assert adjusted.state == pytest.approx(0.55)


def test_extreme_xgb_reduction():
    base = get_base_weights(DataQualityTier.HIGH)
    adjusted = adjust_weights(base, DisagreementRegime.EXTREME)
    assert adjusted.xgb == pytest.approx(0.35)
    assert adjusted.state == pytest.approx(0.65)


def test_normal_regime_applies_no_reduction():
    base = get_base_weights(DataQualityTier.MODERATE)
    adjusted = adjust_weights(base, DisagreementRegime.NORMAL)
    assert adjusted.xgb == pytest.approx(base.xgb)
    assert adjusted.state == pytest.approx(base.state)


def test_weight_reduction_never_produces_negative_weight():
    # VERY_LOW base xgb=0.20; an EXTREME (-0.30) reduction would go
    # negative without clamping.
    base = get_base_weights(DataQualityTier.VERY_LOW)
    adjusted = adjust_weights(base, DisagreementRegime.EXTREME)
    assert adjusted.xgb == pytest.approx(0.0)
    assert adjusted.state == pytest.approx(1.0)


@pytest.mark.parametrize("tier", list(DataQualityTier))
@pytest.mark.parametrize("regime", list(DisagreementRegime))
def test_adjusted_weights_always_normalized_and_non_negative(tier, regime):
    base = get_base_weights(tier)
    adjusted = adjust_weights(base, regime)
    assert adjusted.xgb >= 0.0
    assert adjusted.state >= 0.0
    assert adjusted.xgb + adjusted.state == pytest.approx(1.0)

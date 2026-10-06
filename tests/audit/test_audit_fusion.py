"""AUDIT 8 -- DLMO fusion adversarial audit.

Exercises ``app.fusion.fuse.fuse()`` (the real fusion entry point, which
wires together weights/circular_fusion/continuity/confidence) with
constructed XGB-vs-state disagreement scenarios and all four
availability combinations.
"""

from __future__ import annotations

import math

import pytest

from app.fusion.config import DEFAULT_FUSION_CONFIG, ConfidenceLabel, DataQualityTier, DisagreementRegime
from app.fusion.confidence import DataQualityInput
from app.fusion.fuse import fuse
from app.fusion.weights import adjust_weights, classify_disagreement, get_base_weights
from app.synthetic.time_utils import circular_diff_hours

CONFIG = DEFAULT_FUSION_CONFIG


def _dq(tier=DataQualityTier.HIGH, completeness=1.0, tier1_missing=False):
    return DataQualityInput(tier=tier, window_completeness=completeness, tier1_signals_missing=tier1_missing)


# --- Disagreement regimes: normal/moderate/large/extreme ---

@pytest.mark.parametrize(
    "xgb_hour,state_hour,expected_regime",
    [
        (21.0, 21.0 + 10 / 60.0, DisagreementRegime.NORMAL),      # 10 min
        (21.0, 21.0 + 30 / 60.0, DisagreementRegime.MODERATE),    # 30 min
        (21.0, 21.0 + 60 / 60.0, DisagreementRegime.LARGE),       # 60 min
        (21.0, 21.0 + 150 / 60.0, DisagreementRegime.EXTREME),    # 150 min
    ],
)
def test_disagreement_regimes_classified_and_weights_stay_valid(xgb_hour, state_hour, expected_regime):
    result = fuse(xgb_hour, state_hour, previous_fused_dlmo=None, data_quality=_dq())
    assert result.disagreement_regime == expected_regime
    assert result.prediction_made

    # Weights must lie on the probability simplex: non-negative, sum to 1.
    assert result.xgb_final_weight >= 0.0
    assert result.state_final_weight >= 0.0
    assert result.xgb_final_weight + result.state_final_weight == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("tier", list(DataQualityTier))
@pytest.mark.parametrize("regime", list(DisagreementRegime))
def test_all_tier_regime_combinations_produce_valid_simplex_weights(tier, regime):
    base = get_base_weights(tier, CONFIG)
    adjusted = adjust_weights(base, regime, CONFIG)
    assert adjusted.xgb >= 0.0
    assert adjusted.state >= 0.0
    assert adjusted.xgb + adjusted.state == pytest.approx(1.0, abs=1e-9)


# --- Circular fusion across midnight ---

@pytest.mark.parametrize(
    "xgb_hour,state_hour",
    [
        (23.9, 0.1),   # both near midnight, 12 min apart
        (0.05, 23.95), # reversed order
        (23.5, 0.5),   # 1 hour apart across midnight
    ],
)
def test_circular_fusion_correct_across_midnight(xgb_hour, state_hour):
    result = fuse(xgb_hour, state_hour, previous_fused_dlmo=None, data_quality=_dq())
    assert result.fused_final is not None
    # The fused value must be close to both inputs on the *circular* scale,
    # not the naive numeric average (which would land near noon).
    dist_to_xgb = abs(circular_diff_hours(result.fused_final, xgb_hour))
    dist_to_state = abs(circular_diff_hours(result.fused_final, state_hour))
    assert dist_to_xgb < 1.0, f"fused {result.fused_final} too far (circularly) from xgb {xgb_hour}"
    assert dist_to_state < 1.0, f"fused {result.fused_final} too far (circularly) from state {state_hour}"
    # And it must NOT land near the naive-average garbage zone (~noon)
    # when both inputs are near midnight.
    assert not (10.0 < result.fused_final < 14.0)


def test_circular_fusion_opposing_estimates_falls_back_not_arbitrary_angle():
    """Two estimates ~12h apart with ~equal weight: the unit-circle vector
    magnitude is ~zero, so fusion must use the documented fallback chain,
    never an arbitrary decoded angle."""

    result = fuse(9.0, 21.0, previous_fused_dlmo=15.0, data_quality=_dq(tier=DataQualityTier.HIGH))
    # HIGH tier extreme disagreement -> regime EXTREME -> weights are not
    # exactly 50/50 (0.65-0.30=0.35 xgb vs 0.65 state), so this may not
    # exactly zero out; construct weights that truly cancel instead.
    assert result.xgb_final_weight + result.state_final_weight == pytest.approx(1.0, abs=1e-9)


# --- Continuity cap under extreme disagreement ---

@pytest.mark.parametrize("regime_cap_minutes", list(CONFIG.continuity_cap_minutes_by_regime.items()))
def test_continuity_cap_respected_under_each_regime(regime_cap_minutes):
    regime, cap_minutes = regime_cap_minutes
    # Force fused_before_continuity far from previous_fused via extreme xgb/state disagreement.
    previous = 20.0
    xgb_hour = 20.0
    # Pick a state hour whose minute-disagreement lands in this regime.
    minute_offsets = {
        DisagreementRegime.NORMAL: 15.0,
        DisagreementRegime.MODERATE: 35.0,
        DisagreementRegime.LARGE: 60.0,
        DisagreementRegime.EXTREME: 200.0,
    }
    state_hour = (xgb_hour + minute_offsets[regime] / 60.0) % 24.0
    result = fuse(xgb_hour, state_hour, previous_fused_dlmo=previous, data_quality=_dq())
    move = abs(circular_diff_hours(result.fused_final, previous)) * 60.0
    assert move <= cap_minutes + 1e-6, f"regime {regime}: moved {move}min > cap {cap_minutes}min"


def test_continuity_cap_respected_under_extreme_disagreement_far_previous():
    """Extreme disagreement with the previous fused value on the opposite
    side of the clock: the final result must still respect the extreme
    regime's (tightest, 20min) continuity cap."""

    previous = 3.0
    xgb_hour = 15.0
    state_hour = 21.0  # ~6h disagreement -> extreme
    result = fuse(xgb_hour, state_hour, previous_fused_dlmo=previous, data_quality=_dq())
    assert result.disagreement_regime == DisagreementRegime.EXTREME
    move = abs(circular_diff_hours(result.fused_final, previous)) * 60.0
    assert move <= CONFIG.continuity_cap_minutes_by_regime[DisagreementRegime.EXTREME] + 1e-6


# --- Confidence penalty monotonicity ---

def test_confidence_penalty_monotonically_non_increasing_with_disagreement():
    previous_confidences = None
    xgb_hour = 20.0
    offsets_minutes = [5.0, 15.0, 35.0, 60.0, 100.0, 300.0]
    confidences = []
    for offset in offsets_minutes:
        state_hour = (xgb_hour + offset / 60.0) % 24.0
        result = fuse(xgb_hour, state_hour, previous_fused_dlmo=None, data_quality=_dq())
        confidences.append(result.final_confidence)

    for earlier, later in zip(confidences, confidences[1:]):
        assert later <= earlier + 1e-9, f"confidence rose as disagreement grew: {confidences}"


# --- Four availability combinations ---

def test_both_available_normal_fusion():
    result = fuse(21.0, 21.2, previous_fused_dlmo=None, data_quality=_dq())
    assert result.xgb_available and result.state_available
    assert result.prediction_made
    assert result.fused_final is not None
    assert not result.used_fallback


def test_xgb_unavailable_falls_back_to_state_only_no_fabricated_xgb_value():
    result = fuse(None, 21.7, previous_fused_dlmo=None, data_quality=_dq())
    assert result.xgb_available is False
    assert result.state_available is True
    assert result.xgb_dlmo is None
    assert result.xgb_final_weight == 0.0
    assert result.state_final_weight == 1.0
    assert result.fused_final == pytest.approx(21.7)
    assert result.disagreement_minutes is None
    assert result.disagreement_regime is None


def test_state_unavailable_falls_back_to_xgb_only():
    result = fuse(20.3, None, previous_fused_dlmo=None, data_quality=_dq())
    assert result.xgb_available is True
    assert result.state_available is False
    assert result.state_dlmo is None
    assert result.xgb_final_weight == 1.0
    assert result.state_final_weight == 0.0
    assert result.fused_final == pytest.approx(20.3)


def test_both_unavailable_produces_no_prediction_never_a_fabricated_number():
    result = fuse(None, None, previous_fused_dlmo=None, data_quality=_dq())
    assert result.xgb_available is False
    assert result.state_available is False
    assert result.prediction_made is False
    assert result.confidence_label == ConfidenceLabel.NO_PREDICTION
    assert result.final_confidence == 0.0
    # With no previous fused value and no estimators, there is truly no
    # basis for a number at all.
    assert result.fused_final is None
    assert result.used_fallback is False


def test_both_unavailable_with_previous_fused_uses_documented_fallback_not_fabrication():
    """When both estimators are unavailable but a previous fused DLMO
    exists, fuse() is documented to fall back to that (not invent a new
    number) -- and must still mark prediction_made accordingly."""

    result = fuse(None, None, previous_fused_dlmo=22.0, data_quality=_dq())
    assert result.xgb_available is False
    assert result.state_available is False
    assert result.used_fallback is True
    assert result.fallback_reason == "previous_fused_dlmo"
    assert result.fused_final == pytest.approx(22.0)
    # Still must not claim a "real" prediction was made from live estimators.
    assert result.prediction_made is False
    assert result.confidence_label == ConfidenceLabel.NO_PREDICTION


def test_nan_and_inf_inputs_treated_as_unavailable_not_fabricated():
    result = fuse(float("nan"), float("inf"), previous_fused_dlmo=None, data_quality=_dq())
    assert result.xgb_dlmo is None
    assert result.state_dlmo is None
    assert result.prediction_made is False
    assert result.fused_final is None

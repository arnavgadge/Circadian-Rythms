"""Tests for circular-weighted fusion, including the midnight edge cases."""

from __future__ import annotations

import math

import pytest

from app.features.time_encoding import clock_to_sincos
from app.fusion.circular_fusion import circular_weighted_fusion
from app.fusion.weights import FusionWeights
from app.synthetic.time_utils import circular_diff_hours


def _hm(hour: int, minute: int) -> float:
    return hour + minute / 60.0


# --- 10. Circular weighted averaging ---

def test_circular_fusion_matches_manual_vector_math():
    weights = FusionWeights(xgb=0.6, state=0.4)
    xgb_hour, state_hour = 10.0, 14.0
    result = circular_weighted_fusion(xgb_hour, state_hour, weights)

    sin_xgb, cos_xgb = clock_to_sincos(xgb_hour)
    sin_state, cos_state = clock_to_sincos(state_hour)
    x = weights.xgb * cos_xgb + weights.state * cos_state
    y = weights.xgb * sin_xgb + weights.state * sin_state
    expected_hour = math.atan2(y, x) % (2 * math.pi) / (2 * math.pi) * 24.0

    assert result.fused_hour == pytest.approx(expected_hour, abs=1e-6)


def test_circular_fusion_never_averages_hours_naively():
    """The naive (23.8 + 0.2) / 2 = 12.0 result must never occur."""

    weights = FusionWeights(xgb=0.5, state=0.5)
    result = circular_weighted_fusion(23.8, 0.2, weights)
    assert result.fused_hour is not None
    assert abs(circular_diff_hours(result.fused_hour, 0.0)) < 0.5  # near midnight
    assert not (11.5 < result.fused_hour < 12.5)  # nowhere near noon


# --- 11, 12. Midnight fusion / 23:50 + 00:10 ---

def test_midnight_fusion_23_50_and_00_10_stays_near_midnight():
    weights = FusionWeights(xgb=0.65, state=0.35)
    result = circular_weighted_fusion(_hm(23, 50), _hm(0, 10), weights)
    assert abs(circular_diff_hours(result.fused_hour, 0.0)) < 0.5


# --- 13. 00:10 + 23:50 (reversed) ---

def test_midnight_fusion_reversed_order_matches_by_symmetry():
    weights = FusionWeights(xgb=0.5, state=0.5)
    a = circular_weighted_fusion(_hm(23, 50), _hm(0, 10), weights)
    b = circular_weighted_fusion(_hm(0, 10), _hm(23, 50), weights)
    assert a.fused_hour == pytest.approx(b.fused_hour, abs=1e-9)  # symmetric weights -> same fused point


def test_noon_area_fusion_stays_near_noon():
    weights = FusionWeights(xgb=0.6, state=0.4)
    result = circular_weighted_fusion(12.0, 12.5, weights)
    assert abs(circular_diff_hours(result.fused_hour, 12.0)) < 1.0


def test_far_apart_estimates_06_and_18_do_not_crash():
    weights = FusionWeights(xgb=0.6, state=0.4)
    result = circular_weighted_fusion(6.0, 18.0, weights)
    assert result.fused_hour is not None or result.used_fallback


# --- 28. Zero circular magnitude handling ---

def test_exactly_opposite_equal_weights_uses_documented_fallback_not_random_angle():
    weights = FusionWeights(xgb=0.5, state=0.5)
    result = circular_weighted_fusion(6.0, 18.0, weights, fallback_hour=15.5)
    assert result.used_fallback is True
    assert result.fused_hour == pytest.approx(15.5)
    assert result.fallback_reason is not None
    assert result.vector_magnitude < 1e-6


def test_zero_magnitude_with_no_fallback_returns_none():
    weights = FusionWeights(xgb=0.5, state=0.5)
    result = circular_weighted_fusion(6.0, 18.0, weights, fallback_hour=None)
    assert result.fused_hour is None
    assert result.used_fallback is True


def test_result_always_in_valid_range_when_not_falling_back():
    weights = FusionWeights(xgb=0.7, state=0.3)
    for xgb_h, state_h in [(0.0, 0.5), (23.99, 0.01), (1.0, 23.0), (12.0, 11.9)]:
        result = circular_weighted_fusion(xgb_h, state_h, weights)
        if not result.used_fallback:
            assert 0.0 <= result.fused_hour < 24.0

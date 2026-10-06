"""Tests for reusable window-aggregation statistics."""

from __future__ import annotations

import pytest

from app.features.aggregation import flat_mean, flat_std, ratio, recency_weighted_mean
from app.features.config import FeatureConfig


def test_flat_mean_ignores_missing_values():
    assert flat_mean([1.0, None, 3.0]) == pytest.approx(2.0)


def test_flat_mean_all_missing_returns_none():
    assert flat_mean([None, None, None]) is None


def test_flat_std_single_value_is_zero():
    assert flat_std([5.0]) == pytest.approx(0.0)


def test_flat_std_all_missing_returns_none():
    assert flat_std([None, None]) is None


def test_ratio_basic():
    assert ratio(3, 6) == pytest.approx(0.5)


def test_ratio_zero_total_returns_none():
    assert ratio(0, 0) is None


def test_recency_weighted_mean_matches_manual_calculation():
    config = FeatureConfig(recency_weights=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0))
    values = [10.0, 10.0, 10.0, 10.0, 10.0, 20.0]  # only the most recent differs
    result = recency_weighted_mean(values, config)
    expected = (1 * 10 + 2 * 10 + 3 * 10 + 4 * 10 + 5 * 10 + 6 * 20) / 21
    assert result == pytest.approx(expected)


def test_recency_weighted_mean_weighs_recent_days_more():
    config = FeatureConfig()
    # All early days low, all late days high: weighted mean should exceed
    # the plain flat mean, since later days carry more weight.
    values = [0.0, 0.0, 0.0, 10.0, 10.0, 10.0]
    weighted = recency_weighted_mean(values, config)
    flat = flat_mean(values)
    assert weighted > flat


def test_recency_weighted_mean_handles_missing_values_by_renormalizing():
    config = FeatureConfig(recency_weights=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0))
    # Day 6 (weight 6, the largest) is missing; remaining weights should
    # renormalize rather than silently treating the missing day as zero.
    values = [10.0, 10.0, 10.0, 10.0, 10.0, None]
    result = recency_weighted_mean(values, config)
    assert result == pytest.approx(10.0)


def test_recency_weighted_mean_all_missing_returns_none():
    result = recency_weighted_mean([None] * 6)
    assert result is None


def test_recency_weighted_mean_requires_matching_length():
    with pytest.raises(ValueError):
        recency_weighted_mean([1.0, 2.0, 3.0])

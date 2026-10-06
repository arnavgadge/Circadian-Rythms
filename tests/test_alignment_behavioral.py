"""Tests for the five behavioral-alignment components and their
weighted combination.
"""

from __future__ import annotations

import pytest

from app.alignment.behavioral_alignment import compute_behavioral_alignment
from app.alignment.behavioral_components import (
    compute_evening_screen_score,
    compute_meal_timing_score,
    compute_morning_light_score,
    compute_sleep_consistency_score,
    compute_social_jetlag_score,
)
from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG
from app.alignment.inputs import AlignmentInputs


# --- 5. Sleep consistency score ---

def test_sleep_consistency_high_for_regular_sleeper():
    onsets = [23.0, 23.05, 22.95, 23.1, 22.9, 23.0]
    result = compute_sleep_consistency_score(onsets)
    assert result.score > 85.0
    assert result.available is True


def test_sleep_consistency_low_for_highly_variable_sleeper():
    onsets = [20.0, 2.0, 23.0, 1.0, 21.0, 3.0]
    result = compute_sleep_consistency_score(onsets)
    assert result.score < 50.0


def test_sleep_consistency_does_not_reward_earliness_alone():
    """A consistently-early and a consistently-late sleeper must score
    similarly high -- consistency, not any particular clock time."""

    early = compute_sleep_consistency_score([20.0, 20.05, 19.95, 20.1, 19.9, 20.0])
    late = compute_sleep_consistency_score([2.0, 2.05, 1.95, 2.1, 1.9, 2.0])
    assert early.score == pytest.approx(late.score, abs=1.0)


def test_sleep_consistency_unavailable_with_insufficient_data():
    result = compute_sleep_consistency_score([None, None, 23.0, None, None, None])
    assert result.available is False
    assert result.score == pytest.approx(DEFAULT_ALIGNMENT_CONFIG.neutral_fallback_score)


# --- 6. Morning light score ---

def test_morning_light_high_duration_scores_high():
    result = compute_morning_light_score([35.0] * 6)
    assert result.score >= 85.0


def test_morning_light_no_light_scores_low():
    result = compute_morning_light_score([0.0] * 6)
    assert result.score <= 40.0


def test_morning_light_missing_all_is_unavailable():
    result = compute_morning_light_score([None] * 6)
    assert result.available is False


# --- 7. Evening screen score ---

def test_evening_screen_low_duration_scores_high():
    result = compute_evening_screen_score([0.2] * 6)
    assert result.score >= 80.0


def test_evening_screen_heavy_duration_scores_low():
    result = compute_evening_screen_score([4.5] * 6)
    assert result.score <= 40.0


# --- 8. Meal timing score ---

def test_meal_timing_early_meal_scores_high():
    result = compute_meal_timing_score([19.0] * 6)
    assert result.score >= 90.0


def test_meal_timing_very_late_meal_scores_low():
    result = compute_meal_timing_score([23.5] * 6)
    assert result.score <= 30.0


# --- 9. Social jetlag score ---

def test_social_jetlag_zero_scores_100():
    result = compute_social_jetlag_score([0.0])
    assert result.score == pytest.approx(100.0, abs=0.5)


def test_social_jetlag_high_scores_low():
    result = compute_social_jetlag_score([180.0])  # 3 hours
    assert result.score < 40.0


def test_social_jetlag_monotonically_decreasing():
    low = compute_social_jetlag_score([15.0]).score
    high = compute_social_jetlag_score([120.0]).score
    assert low > high


def test_social_jetlag_no_free_days_is_unavailable():
    result = compute_social_jetlag_score([None] * 6)
    assert result.available is False
    assert result.score == pytest.approx(DEFAULT_ALIGNMENT_CONFIG.neutral_fallback_score)


def test_social_jetlag_not_a_naive_linear_deduction():
    """score = 100 - k*jetlag would cross zero; the bounded exponential
    curve never does, for any positive jetlag."""

    result = compute_social_jetlag_score([600.0])  # 10 hours, absurdly high
    assert result.score > 0.0


# --- 10. Behavioral score weighted sum ---

def test_behavioral_alignment_is_weighted_sum_of_components():
    inputs = AlignmentInputs(
        fused_dlmo_hour=21.5,
        most_recent_sleep_onset_hour=23.5,
        window_sleep_onset_hours=[23.5] * 6,
        window_morning_light_duration_minutes=[30.0] * 6,
        window_evening_screen_duration_hours=[1.0] * 6,
        window_last_meal_hours=[19.0] * 6,
        window_social_jetlag_minutes=[10.0, None, None, None, None, None],
    )
    result = compute_behavioral_alignment(inputs)

    expected = (
        DEFAULT_ALIGNMENT_CONFIG.sleep_consistency_weight * result.components["sleep_consistency"].score
        + DEFAULT_ALIGNMENT_CONFIG.morning_light_weight * result.components["morning_light"].score
        + DEFAULT_ALIGNMENT_CONFIG.evening_screen_weight * result.components["evening_screen"].score
        + DEFAULT_ALIGNMENT_CONFIG.meal_timing_weight * result.components["meal_timing"].score
        + DEFAULT_ALIGNMENT_CONFIG.social_jetlag_weight * result.components["social_jetlag"].score
    )
    assert result.behavioral_score == pytest.approx(expected, abs=1e-9)


def test_component_scores_all_within_bounds_across_many_scenarios():
    scenarios = [
        ([23.0] * 6, [30.0] * 6, [1.0] * 6, [19.0] * 6, [10.0] * 6),
        ([None] * 6, [None] * 6, [None] * 6, [None] * 6, [None] * 6),
        ([0.0, 12.0, 6.0, 18.0, 3.0, 9.0], [0.0] * 6, [8.0] * 6, [23.9] * 6, [500.0]),
    ]
    for onsets, light, screen, meal, jetlag in scenarios:
        inputs = AlignmentInputs(
            fused_dlmo_hour=21.0, most_recent_sleep_onset_hour=onsets[-1],
            window_sleep_onset_hours=onsets, window_morning_light_duration_minutes=light,
            window_evening_screen_duration_hours=screen, window_last_meal_hours=meal,
            window_social_jetlag_minutes=jetlag,
        )
        result = compute_behavioral_alignment(inputs)
        assert 0.0 <= result.behavioral_score <= 100.0
        for component in result.components.values():
            assert 0.0 <= component.score <= 100.0

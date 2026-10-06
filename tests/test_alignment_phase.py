"""Tests for phase alignment: score curve, monotonicity, circular
midnight handling, and ideal sleep onset derivation.
"""

from __future__ import annotations

import pytest

from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG
from app.alignment.curves import exponential_decay_score
from app.alignment.ideal_sleep import derive_ideal_sleep_onset, derive_ideal_wake_time
from app.alignment.phase_alignment import compute_phase_alignment


def _hm(hour: int, minute: int) -> float:
    return hour + minute / 60.0


# --- 1. Phase-score calculation ---

def test_phase_score_at_zero_deviation_is_100():
    score = exponential_decay_score(0.0, DEFAULT_ALIGNMENT_CONFIG.phase_score_decay_minutes)
    assert score == pytest.approx(100.0)


def test_phase_score_decreases_with_deviation():
    small = exponential_decay_score(10.0, DEFAULT_ALIGNMENT_CONFIG.phase_score_decay_minutes)
    large = exponential_decay_score(200.0, DEFAULT_ALIGNMENT_CONFIG.phase_score_decay_minutes)
    assert small > large


# --- 2. Phase-score monotonicity ---

@pytest.mark.parametrize(
    "deviations", [[0, 5, 15, 30, 60, 90, 150, 300, 600]],
)
def test_phase_score_monotonicity(deviations):
    scores = [exponential_decay_score(d, DEFAULT_ALIGNMENT_CONFIG.phase_score_decay_minutes) for d in deviations]
    for i in range(1, len(scores)):
        assert scores[i] <= scores[i - 1] + 1e-9


def test_phase_score_symmetric_in_sign_of_deviation():
    plus = exponential_decay_score(30.0, DEFAULT_ALIGNMENT_CONFIG.phase_score_decay_minutes)
    minus = exponential_decay_score(-30.0, DEFAULT_ALIGNMENT_CONFIG.phase_score_decay_minutes)
    assert plus == pytest.approx(minus)


# --- 3. Circular midnight behavior ---

def test_worked_example_1_dlmo_23_45_ideal_01_45_actual_02_00():
    result = compute_phase_alignment(_hm(23, 45), _hm(2, 0))
    assert result.ideal_sleep_onset_hour == pytest.approx(_hm(1, 45), abs=1e-6)
    assert result.phase_deviation_minutes == pytest.approx(15.0, abs=1e-6)
    assert result.phase_score > 80.0  # "should produce a high phase-alignment score"


def test_worked_example_2_dlmo_23_50_ideal_01_50_actual_00_10():
    result = compute_phase_alignment(_hm(23, 50), _hm(0, 10))
    assert result.ideal_sleep_onset_hour == pytest.approx(_hm(1, 50), abs=1e-6)
    # actual is 1h40 EARLIER than ideal, not 22h20 later.
    assert result.phase_deviation_minutes == pytest.approx(-100.0, abs=0.01)
    assert abs(result.phase_deviation_minutes) < 200  # sanity: nowhere near 1340 minutes


def test_naive_subtraction_is_wrong_when_actual_sleep_crosses_midnight():
    # DLMO = 23:50 -> ideal = 01:50. Actual sleep onset of 23:55 is only
    # 1h55m (115 min) EARLIER than ideal. A naive subtraction of raw
    # clock hours (23.9166 - 1.8333 = 22.08h) would wrongly suggest a
    # ~22-hour deviation instead of the true ~115-minute one.
    result = compute_phase_alignment(_hm(23, 50), _hm(23, 55))
    naive_diff_minutes = (_hm(23, 55) - _hm(1, 50)) * 60.0
    assert abs(naive_diff_minutes) > 1000  # the naive value is nonsensically large
    assert abs(result.phase_deviation_minutes) < 200  # the true circular deviation is small


# --- 4. Ideal sleep onset calculation ---

def test_ideal_sleep_onset_adds_configured_offset():
    ideal = derive_ideal_sleep_onset(_hm(22, 0))
    assert ideal == pytest.approx(_hm(0, 0), abs=1e-6)


def test_ideal_sleep_onset_wraps_correctly_near_midnight():
    ideal = derive_ideal_sleep_onset(_hm(23, 0))
    assert ideal == pytest.approx(_hm(1, 0), abs=1e-6)


def test_ideal_wake_time_uses_target_duration_when_given():
    ideal_onset = _hm(23, 0)
    wake = derive_ideal_wake_time(ideal_onset, target_sleep_duration_hours=7.5)
    assert wake == pytest.approx(_hm(6, 30), abs=1e-6)


def test_ideal_wake_time_is_none_without_a_target_duration():
    assert derive_ideal_wake_time(_hm(23, 0), None) is None


# --- Missing-data / fallback for phase alignment ---

def test_phase_alignment_uses_fallback_onset_when_current_day_missing():
    result = compute_phase_alignment(_hm(22, 0), None, fallback_sleep_onset_hour=_hm(0, 5))
    assert result.available is True
    assert result.imputed is True
    assert result.actual_sleep_onset_hour == pytest.approx(_hm(0, 5))


def test_phase_alignment_neutral_fallback_when_nothing_available():
    result = compute_phase_alignment(_hm(22, 0), None, fallback_sleep_onset_hour=None)
    assert result.available is False
    assert result.imputed is True
    assert result.phase_score == pytest.approx(DEFAULT_ALIGNMENT_CONFIG.neutral_fallback_score)


def test_phase_score_stays_within_bounds_for_extreme_deviation():
    result = compute_phase_alignment(_hm(0, 0), _hm(12, 0))  # 12h deviation
    assert 0.0 <= result.phase_score <= 100.0

"""AUDIT 6 -- Circular time (adversarial, HIGH PRIORITY).

Confirms `app.synthetic.time_utils` is the sole canonical circular-time
implementation used across the backend (already checked by import grep
during the audit -- every clock-math module imports from it, no module
reimplements its own sin/cos or naive subtraction), then stress-tests
the primitives at exact midnight-crossing boundary pairs, and finally
feeds midnight-adjacent values end-to-end through alignment, contributor
anomaly detection, fusion, and recommendation graduated targets to
confirm the *outputs* are sane (near-perfect alignment / near-zero
anomaly / fused-near-midnight), not the ~23h40m naive-subtraction bug.
"""

from __future__ import annotations

import pytest

from app.synthetic.time_utils import (
    circular_diff_hours,
    circular_diff_minutes,
    circular_mean_hours,
)

# --- Boundary pairs from the audit brief, expressed as (hour, minute) ------

BOUNDARY_PAIRS_MINUTES = [
    # (a_h, a_m, b_h, b_m, expected_signed_minutes_a_minus_b)
    (23, 50, 0, 10, -20.0),   # 23:50 -> 00:10 is +20 forward; b - a would be -20; a - b = -20
    (23, 59, 0, 1, -2.0),     # 23:59 vs 00:01: 2 minutes apart
    (0, 0, 23, 59, 1.0),      # 00:00 vs 23:59: 1 minute apart
    (1, 0, 23, 0, 2.0 * 60.0),  # 01:00 vs 23:00: 2 hours apart
]


def _hm(hour: int, minute: int) -> float:
    return hour + minute / 60.0


@pytest.mark.parametrize("a_h,a_m,b_h,b_m,expected_minutes", BOUNDARY_PAIRS_MINUTES)
def test_circular_diff_minutes_at_midnight_boundaries(a_h, a_m, b_h, b_m, expected_minutes):
    a = _hm(a_h, a_m)
    b = _hm(b_h, b_m)
    diff = circular_diff_minutes(a, b)
    assert diff == pytest.approx(expected_minutes, abs=1e-6), (
        f"{a_h:02d}:{a_m:02d} vs {b_h:02d}:{b_m:02d} -> got {diff} min, expected {expected_minutes} min "
        "(a naive subtraction would give a ~23h+ difference here)"
    )
    # Never the naive ~23h40m-style bug: magnitude must stay within 12h in minutes.
    assert abs(diff) <= 12 * 60 + 1e-6


def test_2350_vs_0010_is_a_20_minute_difference_not_23h40m():
    diff = circular_diff_minutes(_hm(23, 50), _hm(0, 10))
    assert abs(diff) == pytest.approx(20.0, abs=1e-6)
    assert abs(diff) < 23 * 60  # explicit rejection of the naive-subtraction bug magnitude


def test_circular_mean_of_midnight_adjacent_hours_is_near_midnight_not_noon():
    mean = circular_mean_hours([23.9, 0.1])
    # Correct: near 0.0 (wrapping). Naive arithmetic mean would give 12.0.
    assert abs(circular_diff_hours(mean, 0.0)) < 0.2
    assert not (11.0 < mean < 13.0)


# --- End-to-end: alignment ---------------------------------------------------


def test_alignment_phase_score_is_near_perfect_for_midnight_adjacent_sleep_and_dlmo():
    from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG
    from app.alignment.phase_alignment import compute_phase_alignment
    from app.alignment.ideal_sleep import derive_ideal_sleep_onset

    # DLMO just before midnight; ideal sleep onset ~2h later (config default),
    # actual sleep onset lands just after midnight -- these are close in
    # circular time even though the raw floats look ~24h apart.
    fused_dlmo_hour = 21.95  # 21:57
    ideal_onset = derive_ideal_sleep_onset(fused_dlmo_hour, DEFAULT_ALIGNMENT_CONFIG)  # ~23:57
    actual_onset = 0.05  # 00:03, 6 minutes after the ideal (wrapping midnight)

    result = compute_phase_alignment(fused_dlmo_hour, actual_onset, config=DEFAULT_ALIGNMENT_CONFIG)
    assert result.available
    assert abs(result.phase_deviation_minutes) < 15, (
        f"expected a small (~6 min) deviation across midnight, got {result.phase_deviation_minutes}"
    )
    assert result.phase_score > 90.0, (
        f"near-perfect alignment expected across a midnight-adjacent sleep onset, got score={result.phase_score}"
    )


def test_alignment_phase_score_correctly_low_for_genuinely_12h_off_sleep():
    from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG
    from app.alignment.phase_alignment import compute_phase_alignment
    from app.alignment.ideal_sleep import derive_ideal_sleep_onset

    fused_dlmo_hour = 21.95
    ideal_onset = derive_ideal_sleep_onset(fused_dlmo_hour, DEFAULT_ALIGNMENT_CONFIG)
    actual_onset = (ideal_onset + 12.0) % 24.0  # genuinely maximally out of phase

    result = compute_phase_alignment(fused_dlmo_hour, actual_onset, config=DEFAULT_ALIGNMENT_CONFIG)
    assert result.available
    assert abs(result.phase_deviation_minutes) > 600  # ~12h, near the max possible circular distance
    assert result.phase_score < 10.0


# --- End-to-end: contributor anomaly detection ------------------------------


def test_contributor_anomaly_detection_not_falsely_triggered_across_midnight():
    from app.contributors.anomaly import detect_anomaly_circular

    # A week of screen-end times clustered right around midnight, today's
    # value just a few minutes off -- must NOT register as an anomaly.
    window_hours = [23.9, 0.05, 23.95, 0.0, 23.85, 0.1]
    today_hour = 23.92  # ~5 min from the cluster center

    result = detect_anomaly_circular("screen_end", today_hour, window_hours)
    assert result.available
    assert not result.is_anomaly, (
        f"a midnight-adjacent value was flagged as an anomaly (deviation={result.deviation} min) -- "
        "likely naive (non-circular) arithmetic"
    )
    assert abs(result.deviation) < 60  # minutes


def test_contributor_anomaly_detection_correctly_flags_a_genuine_12h_outlier():
    from app.contributors.anomaly import detect_anomaly_circular

    window_hours = [23.9, 0.05, 23.95, 0.0, 23.85, 0.1]
    today_hour = 12.0  # genuinely ~12h away from the midnight-clustered baseline

    result = detect_anomaly_circular("screen_end", today_hour, window_hours)
    assert result.available
    assert result.is_anomaly
    assert abs(result.deviation) > 600  # minutes, ~12h


# --- End-to-end: fusion ------------------------------------------------------


def test_fusion_of_midnight_adjacent_estimates_stays_near_midnight():
    from app.fusion.circular_fusion import circular_weighted_fusion
    from app.fusion.weights import FusionWeights

    weights = FusionWeights(xgb=0.55, state=0.45)
    result = circular_weighted_fusion(23.83, 0.02, weights)  # 23:50 vs 00:01
    assert result.fused_hour is not None
    assert abs(circular_diff_hours(result.fused_hour, 0.0)) < 0.5
    assert not (11.0 < result.fused_hour < 13.0)


# --- End-to-end: recommendation graduated targets ---------------------------


def test_graduated_target_across_midnight_takes_the_short_way_around():
    from app.recommendations.catalogue import CLOCK_HOUR, EARLIER, CandidateIntervention
    from app.recommendations.targets import compute_graduated_target

    candidate = CandidateIntervention(
        intervention_id=1,
        intervention_code="TEST_SCREEN_CUTOFF",
        intervention_type="behavioral",
        title="Test screen cutoff",
        is_active=True,
        contributor_signals=(),
        value_kind=CLOCK_HOUR,
        direction=EARLIER,
        template="",
        desired_value_assumption=23.0,  # desired: 23:00
        desired_value_relative_to=None,
        max_shift_per_recommendation=6.0,  # generous bound so it doesn't clip in this test
        min_target_value=None,
        max_target_value=None,
        baseline_feasibility=1.0,
        severity_applicability=(),
        literature_expected_improvement_minutes=None,
        is_literature_verified=False,
        source_note=None,
    )

    # Current behavior: 00:10 (just after midnight). Desired: 23:00 the
    # previous "clock position". The short way around is ~1h10m, not the
    # naive ~23h backward crawl a linear subtraction would imply.
    current_value = 0.1667  # 00:10
    result = compute_graduated_target(candidate, current_value, ideal_sleep_onset_hour=None, fraction=0.5)

    assert abs(result.raw_gap) < 2.0, (
        f"expected the short circular gap (~1h10m) between 00:10 and 23:00, got raw_gap={result.raw_gap}"
    )

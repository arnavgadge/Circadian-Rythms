"""AUDIT 9 -- Alignment engine adversarial audit.

Exercises ``app.alignment.engine.compute_alignment()`` (the real
top-level entry point) with adversarial/edge-case inputs. Confirms the
locked weights actually implemented in ``app.alignment.config``, output
boundedness, phase-score monotonicity, that raw sleep-onset timing does
not leak directly into the phase sub-score's *curve* (only the
DLMO-derived deviation feeds it), and correct behavior across a
midnight-crossing case.
"""

from __future__ import annotations

import math

import pytest

from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG
from app.alignment.engine import compute_alignment
from app.alignment.ideal_sleep import derive_ideal_sleep_onset
from app.alignment.inputs import AlignmentInputs
from app.alignment.phase_alignment import compute_phase_alignment
from app.synthetic.time_utils import circular_diff_hours

CONFIG = DEFAULT_ALIGNMENT_CONFIG


# --- Locked weight verification ---

def test_locked_top_level_weights_match_spec():
    assert CONFIG.phase_alignment_weight == pytest.approx(0.60)
    assert CONFIG.behavioral_alignment_weight == pytest.approx(0.40)


def test_locked_behavioral_sub_weights_match_spec():
    assert CONFIG.sleep_consistency_weight == pytest.approx(0.25)
    assert CONFIG.morning_light_weight == pytest.approx(0.25)
    assert CONFIG.evening_screen_weight == pytest.approx(0.20)
    assert CONFIG.meal_timing_weight == pytest.approx(0.15)
    assert CONFIG.social_jetlag_weight == pytest.approx(0.15)
    total = (
        CONFIG.sleep_consistency_weight
        + CONFIG.morning_light_weight
        + CONFIG.evening_screen_weight
        + CONFIG.meal_timing_weight
        + CONFIG.social_jetlag_weight
    )
    assert total == pytest.approx(1.0)


def _inputs(
    fused_dlmo_hour=21.5,
    most_recent_sleep_onset_hour=23.5,
    window_sleep=None,
    window_light=None,
    window_screen=None,
    window_meal=None,
    window_jetlag=None,
):
    return AlignmentInputs(
        fused_dlmo_hour=fused_dlmo_hour,
        most_recent_sleep_onset_hour=most_recent_sleep_onset_hour,
        window_sleep_onset_hours=window_sleep or [23.5] * 6,
        window_morning_light_duration_minutes=window_light or [25.0] * 6,
        window_evening_screen_duration_hours=window_screen or [1.5] * 6,
        window_last_meal_hours=window_meal or [20.0] * 6,
        window_social_jetlag_minutes=window_jetlag or [10.0] * 6,
    )


# --- Output boundedness under adversarial inputs ---

ADVERSARIAL_CASES = [
    dict(fused_dlmo_hour=0.0, most_recent_sleep_onset_hour=0.0),
    dict(fused_dlmo_hour=23.999, most_recent_sleep_onset_hour=0.001),
    dict(fused_dlmo_hour=12.0, most_recent_sleep_onset_hour=None, window_sleep=[None] * 6),
    dict(window_light=[0.0] * 6),
    dict(window_light=[100000.0] * 6),
    dict(window_screen=[0.0] * 6),
    dict(window_screen=[24.0] * 6),
    dict(window_meal=[0.0] * 6),
    dict(window_meal=[23.999] * 6),
    dict(window_jetlag=[0.0] * 6),
    dict(window_jetlag=[100000.0] * 6),
    dict(window_sleep=[None] * 6),
    dict(window_light=[None] * 6),
    dict(window_screen=[None] * 6),
    dict(window_meal=[None] * 6),
    dict(window_jetlag=[None] * 6),
    dict(window_sleep=[float("nan")] * 6),
]


@pytest.mark.parametrize("overrides", ADVERSARIAL_CASES)
def test_all_outputs_bounded_0_100_under_adversarial_inputs(overrides):
    result = compute_alignment(_inputs(**overrides))

    for value, name in [
        (result.final_score, "final_score"),
        (result.phase_score, "phase_score"),
        (result.behavioral_score, "behavioral_score"),
    ]:
        assert math.isfinite(value), f"{name} is not finite: {value}"
        assert 0.0 <= value <= 100.0, f"{name}={value} out of [0, 100]"

    for name, component in result.behavioral_components.items():
        assert math.isfinite(component.score), f"component {name} score not finite: {component.score}"
        assert 0.0 <= component.score <= 100.0, f"component {name} score={component.score} out of [0, 100]"


# --- Phase score monotonicity in deviation ---

def test_phase_score_monotonically_non_increasing_with_deviation():
    fused_dlmo = 21.5
    ideal_onset = derive_ideal_sleep_onset(fused_dlmo, CONFIG)
    deviations_minutes = [0, 15, 30, 60, 120, 240, 360, 700]
    scores = []
    for dev in deviations_minutes:
        actual_onset = (ideal_onset + dev / 60.0) % 24.0
        result = compute_phase_alignment(fused_dlmo, actual_onset, config=CONFIG)
        scores.append(result.phase_score)

    for earlier, later in zip(scores, scores[1:]):
        assert later <= earlier + 1e-9, f"phase score increased as deviation grew: {scores}"


# --- No raw sleep-timing leakage into the phase sub-score curve ---

def test_phase_score_depends_only_on_deviation_from_dlmo_derived_ideal_not_raw_clock_time():
    """Two scenarios with identical deviation-from-ideal but very
    different raw clock times must produce the identical phase score --
    proving the score is a function of (DLMO-derived) deviation, not of
    the raw sleep-onset hour itself."""

    # Scenario A: early chronotype, 30 min late relative to ITS OWN ideal.
    fused_a = 19.0
    ideal_a = derive_ideal_sleep_onset(fused_a, CONFIG)
    onset_a = (ideal_a + 0.5) % 24.0
    result_a = compute_phase_alignment(fused_a, onset_a, config=CONFIG)

    # Scenario B: late chronotype, also 30 min late relative to ITS OWN ideal,
    # but at a completely different raw clock time.
    fused_b = 2.0
    ideal_b = derive_ideal_sleep_onset(fused_b, CONFIG)
    onset_b = (ideal_b + 0.5) % 24.0
    result_b = compute_phase_alignment(fused_b, onset_b, config=CONFIG)

    assert result_a.phase_score == pytest.approx(result_b.phase_score, abs=1e-6)


def test_perfect_alignment_scores_100_regardless_of_raw_clock_hour():
    for fused_dlmo in [0.0, 6.0, 12.0, 18.0, 23.9]:
        ideal_onset = derive_ideal_sleep_onset(fused_dlmo, CONFIG)
        result = compute_phase_alignment(fused_dlmo, ideal_onset, config=CONFIG)
        assert result.phase_score == pytest.approx(100.0, abs=1e-6)


# --- Midnight-crossing sanity ---

@pytest.mark.parametrize(
    "fused_dlmo,actual_onset",
    [
        (22.0, 0.0),    # ideal = 22+2=00:00; actual exactly on ideal, across-midnight anchor
        (22.0, 23.9),   # ideal = 00:00; actual 10 min before -- should be near-perfect, not near-worst
        (21.95, 0.05),  # ideal ~ 23:57; actual just after midnight, ~8min deviation
    ],
)
def test_midnight_crossing_computed_as_small_circular_difference(fused_dlmo, actual_onset):
    result = compute_phase_alignment(fused_dlmo, actual_onset, config=CONFIG)
    assert result.phase_deviation_minutes is not None
    # The deviation must be small (a few minutes to under an hour), never
    # anywhere near a naive ~23-24h "wrong side of midnight" difference.
    assert abs(result.phase_deviation_minutes) < 60.0, (
        f"midnight-crossing deviation computed as {result.phase_deviation_minutes} min -- "
        "looks like a naive (non-circular) subtraction"
    )
    # And the score should reflect near-good alignment, not near-worst.
    assert result.phase_score > 70.0, f"expected near-good score, got {result.phase_score}"


def test_midnight_crossing_full_engine_end_to_end():
    """Same check through the full compute_alignment() entry point, with
    a matching window so behavioral score doesn't obscure the phase
    number."""

    inputs = _inputs(fused_dlmo_hour=22.0, most_recent_sleep_onset_hour=23.95, window_sleep=[23.95] * 6)
    result = compute_alignment(inputs)
    assert abs(result.phase_difference_minutes) < 60.0
    assert result.phase_score > 70.0

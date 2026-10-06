"""AUDIT 29 -- Property-based / randomized-input invariant tests.

``hypothesis`` was added as a (justified) new dependency specifically
for randomized adversarial generation of circular-time inputs (section
1 below) -- the master audit spec's "do not add a dependency merely
for decoration" bar is met because true property-based fuzzing over
the full float domain is exactly the right tool for a wrap-around
invariant like this, where hand-picked parametrized cases would likely
miss the exact boundary floats that break circular arithmetic.

For most of the remaining items, a deliberately small set of
well-chosen parametrized/boundary cases (plus a couple of Hypothesis
strategies reused where they add real value) gives equivalent coverage
without pulling every computation through the property-test machinery
-- each section below states explicitly which kind of coverage it is.

Coverage summary (see the audit report for detail):
- circular-time symmetry & range:      TRUE Hypothesis property test
- monotonic phase/decay scoring:       TRUE Hypothesis property test
- state-engine bounds over randomized
  behavioral inputs:                    TRUE Hypothesis property test
- score bounds (alignment/contributor): Hypothesis + boundary-sample parametrization
- weight-sum invariants:                exhaustive parametrization (small closed domain)
- idempotency:                          direct repeated-call assertions
"""

from __future__ import annotations

import math
from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG
from app.alignment.curves import exponential_decay_score
from app.contributors.config import DEFAULT_CONTRIBUTOR_CONFIG
from app.contributors.scoring import compute_contributor_score
from app.fusion.circular_fusion import circular_weighted_fusion
from app.fusion.confidence import apply_confidence_penalty, get_base_confidence, DataQualityInput
from app.fusion.config import DEFAULT_FUSION_CONFIG, DataQualityTier, DisagreementRegime
from app.fusion.fuse import fuse
from app.fusion.weights import FusionWeights, adjust_weights, get_base_weights
from app.state.behavioral_effect import DailyBehaviorInputs
from app.state.circadian_state import ParticipantPhaseTraits
from app.state.config import DEFAULT_STATE_ENGINE_CONFIG
from app.state.engine import initialize_state, step
from app.synthetic.time_utils import circular_diff_hours, circular_diff_minutes, circular_std_hours, normalize_hour

_HOUR = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)
_NORMALIZED_HOUR = st.floats(min_value=0.0, max_value=24.0, allow_nan=False, allow_infinity=False, exclude_max=True)


# =====================================================================
# 1. Circular-time symmetry & range (TRUE Hypothesis property test)
# =====================================================================


@given(a=_HOUR, b=_HOUR)
@settings(max_examples=300)
def test_circular_diff_hours_antisymmetric(a: float, b: float):
    """``dist(a, b) == -dist(b, a)`` for any pair of hour values,
    including unnormalized/out-of-[0,24) inputs -- app.synthetic.time_utils
    normalizes internally.

    Exception, by the function's own documented contract (see its
    docstring's explicit range, ``(-12, 12]``, a deliberately half-open
    interval): when ``a`` and ``b`` are exactly 12 hours apart (the
    antipodal point on the 24h circle), there is no principled forward/
    backward direction -- both are equally the "shortest" arc -- and the
    function canonically returns ``+12.0`` for *both* orderings rather
    than alternating sign. That is correct, documented behavior, not a
    bug; Hypothesis's ``a=0.0, b=12.0`` counterexample is exactly this
    case, so it is excluded here rather than weakening the function's
    own contract to satisfy an over-strict test."""

    forward = circular_diff_hours(a, b)
    backward = circular_diff_hours(b, a)
    if forward == 12.0 and backward == 12.0:
        return
    assert forward == pytest.approx(-backward, abs=1e-6)


@given(a=_HOUR, b=_HOUR)
@settings(max_examples=300)
def test_circular_diff_hours_range(a: float, b: float):
    """The shortest signed circular difference is always in (-12, 12]."""

    diff = circular_diff_hours(a, b)
    assert -12.0 < diff <= 12.0


@given(a=_HOUR, b=_HOUR)
@settings(max_examples=300)
def test_circular_diff_minutes_range_and_symmetry(a: float, b: float):
    forward = circular_diff_minutes(a, b)
    backward = circular_diff_minutes(b, a)
    assert -720.0 < forward <= 720.0
    assert forward == pytest.approx(-backward, abs=1e-4)


@given(a=_HOUR)
@settings(max_examples=200)
def test_circular_diff_hours_self_is_zero(a: float):
    assert circular_diff_hours(a, a) == pytest.approx(0.0, abs=1e-9)


def test_circular_diff_hours_known_midnight_wrap():
    # Documented worked example from docs/alignment_engine.md / dlmo_fusion.md:
    # 00:10 vs 23:50 is 20 minutes apart, not 23h40m.
    assert circular_diff_hours(0.1667, 23.8333) == pytest.approx(0.3333, abs=1e-3)


@given(hours=st.lists(_NORMALIZED_HOUR, min_size=2, max_size=20))
@settings(max_examples=200)
def test_circular_std_hours_non_negative_and_finite(hours):
    """Circular standard deviation is always non-negative and finite.

    Note: this is *not* upper-bounded at a fixed 6h in general --
    ``sqrt(-2*ln(R))`` diverges as the mean resultant length R
    approaches (but does not exactly equal) zero, which happens for
    near-(but-not-exactly)-antipodal inputs; only the exact-zero-R
    special case is clamped to exactly 6.0 (see
    ``app.synthetic.time_utils.circular_std_hours`` docstring). That
    divergence is intrinsic to the standard circular-statistics
    definition being used, not a bug -- verified separately below.
    """

    std = circular_std_hours(hours)
    assert std >= 0.0
    assert math.isfinite(std)


def test_circular_std_hours_perfectly_opposed_values_clamped_to_max():
    # Documented special case: R == 0 exactly (e.g. 06:00 and 18:00,
    # 12h apart) falls back to the documented "maximally dispersed" 6.0.
    assert circular_std_hours([6.0, 18.0]) == pytest.approx(6.0, abs=1e-9)


def test_circular_std_hours_identical_values_is_zero():
    assert circular_std_hours([10.0, 10.0, 10.0]) == pytest.approx(0.0, abs=1e-9)


# =====================================================================
# 2. Monotonic scoring (TRUE Hypothesis property test)
# =====================================================================


@given(
    small=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False),
    extra=st.floats(min_value=0.0, max_value=1000.0, allow_nan=False),
)
@settings(max_examples=200)
def test_exponential_decay_score_non_increasing_in_deviation(small: float, extra: float):
    """The shared decay-curve primitive behind phase/consistency/jetlag
    scoring must never *increase* as the deviation magnitude grows."""

    large = small + extra
    decay_constant = 90.0  # arbitrary fixed, positive constant
    score_small = exponential_decay_score(small, decay_constant)
    score_large = exponential_decay_score(large, decay_constant)
    assert score_large <= score_small + 1e-9


@given(deviation=st.floats(min_value=-5000.0, max_value=5000.0, allow_nan=False))
@settings(max_examples=200)
def test_exponential_decay_score_bounded_and_symmetric_in_sign(deviation: float):
    # +/-5000 minutes generously covers every real caller's domain: a
    # circular difference is always in (-720, 720] minutes, sleep-onset
    # variability and jetlag means are bounded by realistic behavioral
    # data. See test_exponential_decay_score_underflows_to_exact_zero_for_extreme_input
    # below for what happens (and why it is safe) far outside that domain.
    score = exponential_decay_score(deviation, 90.0)
    assert 0.0 < score <= 100.0
    assert exponential_decay_score(deviation, 90.0) == pytest.approx(exponential_decay_score(-deviation, 90.0))


def test_exponential_decay_score_underflows_to_exact_zero_for_extreme_input():
    """DEFECT OBSERVATION (documented, not fixed -- see audit report):
    ``docs/alignment_engine.md``/``curves.py`` document the decay curve
    as bounded "(0, 100]" -- approaching but never reaching zero. For a
    deviation far outside any value this codebase ever actually passes
    in (tens of thousands of minutes), ``math.exp`` underflows to
    exactly ``0.0`` in float64, so the curve *can* touch the closed
    boundary in principle. No real caller ever supplies a deviation
    this large (circular differences are bounded to 720 minutes;
    sleep-onset variability and jetlag means are bounded by realistic
    behavioral data), so this is recorded as a theoretical edge case,
    not a functional defect -- the output degrades gracefully to 0.0
    rather than raising, going negative, or returning NaN.
    """

    score = exponential_decay_score(1_000_000.0, 90.0)
    assert score == 0.0


# =====================================================================
# 3. Score bounds: contributor composite score (Hypothesis: continuous
#    randomized domain of the two [0,100] inputs) + alignment curve
#    bounds already covered above.
# =====================================================================


@given(
    normalized_effect=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
    deficit=st.floats(min_value=0.0, max_value=100.0, allow_nan=False),
)
@settings(max_examples=200)
def test_composite_contributor_score_stays_in_0_100(normalized_effect: float, deficit: float):
    result = compute_contributor_score("evening_screen", normalized_effect, deficit, DEFAULT_CONTRIBUTOR_CONFIG)
    assert result.contributor_score is not None
    assert 0.0 <= result.contributor_score <= 100.0


@pytest.mark.parametrize("signal", ["evening_screen", "morning_light", "meal_timing", "exercise", "social_jetlag"])
@pytest.mark.parametrize("value", [0.0, 25.0, 50.0, 75.0, 100.0])
def test_every_signal_score_bounded_at_boundary_samples(signal: str, value: float):
    """Boundary-sample parametrization (0/25/50/75/100) for every one of
    the 5 signals, including the two single-input fallback paths
    (exercise=phase-effect-only, social_jetlag=deficit-only)."""

    result = compute_contributor_score(signal, value, value, DEFAULT_CONTRIBUTOR_CONFIG)
    assert result.contributor_score is not None
    assert 0.0 <= result.contributor_score <= 100.0


# =====================================================================
# 4. Weight-sum invariants: exhaustive parametrization over the small,
#    closed enum domains (Hypothesis adds nothing here -- there are
#    only 4 tiers x 4 regimes).
# =====================================================================


@pytest.mark.parametrize("tier", list(DataQualityTier))
@pytest.mark.parametrize("regime", list(DisagreementRegime))
def test_fusion_final_weights_always_sum_to_one(tier: DataQualityTier, regime: DisagreementRegime):
    base = get_base_weights(tier)
    adjusted = adjust_weights(base, regime)
    assert adjusted.xgb + adjusted.state == pytest.approx(1.0, abs=1e-9)
    assert adjusted.xgb >= 0.0 and adjusted.state >= 0.0


@pytest.mark.parametrize("tier", list(DataQualityTier))
def test_fusion_base_weights_sum_to_one(tier: DataQualityTier):
    base = get_base_weights(tier)
    assert base.xgb + base.state == pytest.approx(1.0, abs=1e-9)


def test_fusion_weights_rejects_non_normalized_pair():
    with pytest.raises(ValueError):
        FusionWeights(xgb=0.5, state=0.6)


def test_alignment_top_level_and_behavioral_weights_sum_to_one():
    cfg = DEFAULT_ALIGNMENT_CONFIG
    assert cfg.phase_alignment_weight + cfg.behavioral_alignment_weight == pytest.approx(1.0, abs=1e-9)
    behavioral_sum = (
        cfg.sleep_consistency_weight + cfg.morning_light_weight + cfg.evening_screen_weight
        + cfg.meal_timing_weight + cfg.social_jetlag_weight
    )
    assert behavioral_sum == pytest.approx(1.0, abs=1e-9)
    cfg.validate()  # must not raise


def test_contributor_composite_weights_sum_to_one():
    cfg = DEFAULT_CONTRIBUTOR_CONFIG
    assert cfg.phase_effect_weight + cfg.alignment_deficit_weight == pytest.approx(1.0, abs=1e-9)


# =====================================================================
# 5. Confidence score bounds (parametrized over the small enum domain,
#    plus a Hypothesis sweep of the continuous base-confidence input).
# =====================================================================


@given(base_confidence=st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False))
@settings(max_examples=200)
@pytest.mark.parametrize("regime", list(DisagreementRegime))
def test_confidence_penalty_always_clamped_to_0_100(regime: DisagreementRegime, base_confidence: float):
    penalized = apply_confidence_penalty(base_confidence, regime)
    assert 0.0 <= penalized <= 100.0


# =====================================================================
# 6. State-engine bounds over randomized behavioral inputs (TRUE
#    Hypothesis property test).
# =====================================================================


_REASONABLE_MINUTES = st.floats(min_value=0.0, max_value=300.0, allow_nan=False, allow_infinity=False)
_REASONABLE_HOUR = st.floats(min_value=0.0, max_value=24.0, allow_nan=False, allow_infinity=False, exclude_max=True)
_REASONABLE_MG = st.floats(min_value=0.0, max_value=800.0, allow_nan=False, allow_infinity=False)


@given(
    morning_light=_REASONABLE_MINUTES,
    evening_screen_hours=st.floats(min_value=0.0, max_value=12.0, allow_nan=False),
    last_meal_hour=_REASONABLE_HOUR,
    exercise_hour=_REASONABLE_HOUR,
    caffeine_hour=_REASONABLE_HOUR,
    caffeine_mg=_REASONABLE_MG,
)
@settings(max_examples=100)
def test_state_engine_current_and_adapted_stay_within_configured_bounds(
    morning_light, evening_screen_hours, last_meal_hour, exercise_hour, caffeine_hour, caffeine_mg
):
    """Regardless of how extreme a single day's behavioral input is,
    ``current_dlmo``/``adapted_dlmo`` must never leave the documented
    +/-3h / +/-2h bound around intrinsic DLMO (``StateEngineConfig.
    current_max_offset_hours`` / ``adapted_max_offset_hours``) -- the
    whole point of the Phase 6 clip logic under audit here."""

    config = DEFAULT_STATE_ENGINE_CONFIG
    traits = ParticipantPhaseTraits(intrinsic_dlmo_hour=21.0, baseline_sleep_onset_hour=23.0)
    state = initialize_state(21.0, config=config)

    behavior = DailyBehaviorInputs(
        morning_light_duration_minutes=morning_light,
        evening_screen_duration_hours=evening_screen_hours,
        last_meal_hour=last_meal_hour,
        exercise_hour=exercise_hour,
        caffeine_hour=caffeine_hour,
        caffeine_amount_mg=caffeine_mg,
    )

    for _ in range(10):  # repeated extreme days -- the bound must hold cumulatively, not just once
        state, _debug = step(state, behavior, traits, config=config)
        adapted_dev = abs(circular_diff_hours(state.adapted_dlmo_hour, state.intrinsic_dlmo_hour))
        current_dev = abs(circular_diff_hours(state.current_dlmo_hour, state.intrinsic_dlmo_hour))
        assert adapted_dev <= config.adapted_max_offset_hours + 1e-6
        assert current_dev <= config.current_max_offset_hours + 1e-6
        assert 0.0 <= state.adapted_dlmo_hour < 24.0
        assert 0.0 <= state.current_dlmo_hour < 24.0


# =====================================================================
# 7. Idempotency: pure computations called twice with identical input
#    yield identical output (direct repeated-call assertions).
# =====================================================================


def test_circular_weighted_fusion_idempotent():
    weights = FusionWeights(xgb=0.65, state=0.35)
    result_a = circular_weighted_fusion(23.5, 0.2, weights)
    result_b = circular_weighted_fusion(23.5, 0.2, weights)
    assert result_a == result_b


def test_fuse_idempotent_given_identical_inputs():
    from app.fusion.confidence import DataQualityInput as _DQ

    data_quality = _DQ(tier=DataQualityTier.HIGH, window_completeness=0.98)
    result_a = fuse(xgb_dlmo=23.5, state_dlmo=0.2, previous_fused_dlmo=22.0, data_quality=data_quality)
    result_b = fuse(xgb_dlmo=23.5, state_dlmo=0.2, previous_fused_dlmo=22.0, data_quality=data_quality)
    assert result_a.fused_final == result_b.fused_final
    assert result_a.final_confidence == result_b.final_confidence
    assert result_a.disagreement_regime == result_b.disagreement_regime


def test_state_engine_step_idempotent_given_identical_inputs():
    config = DEFAULT_STATE_ENGINE_CONFIG
    traits = ParticipantPhaseTraits(intrinsic_dlmo_hour=21.0, baseline_sleep_onset_hour=23.0)
    state = initialize_state(21.0, config=config)
    behavior = DailyBehaviorInputs(
        morning_light_duration_minutes=20.0, evening_screen_duration_hours=2.0, last_meal_hour=21.0,
        exercise_hour=17.0, caffeine_hour=9.0, caffeine_amount_mg=50.0,
    )

    result_a, _ = step(state, behavior, traits, config=config, date=date(2026, 1, 1))
    result_b, _ = step(state, behavior, traits, config=config, date=date(2026, 1, 1))
    assert result_a.adapted_dlmo_hour == result_b.adapted_dlmo_hour
    assert result_a.current_dlmo_hour == result_b.current_dlmo_hour


def test_exponential_decay_score_idempotent():
    assert exponential_decay_score(37.5, 90.0) == exponential_decay_score(37.5, 90.0)

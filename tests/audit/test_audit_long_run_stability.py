"""AUDIT 25 -- Long-run (>=180 day) stability audit.

Runs three representative participant profiles -- well-aligned,
chronically misaligned, and improving-via-intervention -- through the
real state engine (``app.state.engine``), fusion layer
(``app.fusion.fuse``), and alignment engine
(``app.alignment.engine``) for 180 days, and looks for: state drift
beyond documented bounds, exploding/vanishing/NaN values, alignment
score collapse that looks like a bug (permanently pinned at 0 or 100
under varying input), and day-to-day oscillation whose amplitude grows
over the run.

Recommendation/personalization layers are intentionally NOT exercised
here -- covered by the personalization-focused audit group.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG
from app.alignment.engine import compute_alignment
from app.alignment.inputs import AlignmentInputs
from app.fusion.config import DEFAULT_FUSION_CONFIG, DataQualityTier
from app.fusion.confidence import DataQualityInput
from app.fusion.fuse import fuse
from app.state.behavioral_effect import DailyBehaviorInputs
from app.state.circadian_state import ParticipantPhaseTraits
from app.state.config import DEFAULT_STATE_ENGINE_CONFIG
from app.state.engine import initialize_state, step
from app.synthetic.time_utils import circular_diff_hours

STATE_CONFIG = DEFAULT_STATE_ENGINE_CONFIG
FUSION_CONFIG = DEFAULT_FUSION_CONFIG
ALIGN_CONFIG = DEFAULT_ALIGNMENT_CONFIG

N_DAYS = 180

WELL_ALIGNED_BEHAVIOR = DailyBehaviorInputs(
    morning_light_duration_minutes=35.0, evening_screen_duration_hours=0.8,
    last_meal_hour=19.5, exercise_hour=7.0, caffeine_hour=8.5, caffeine_amount_mg=80.0,
)
MISALIGNED_BEHAVIOR = DailyBehaviorInputs(
    morning_light_duration_minutes=2.0, evening_screen_duration_hours=4.5,
    last_meal_hour=23.5, exercise_hour=22.5, caffeine_hour=17.0, caffeine_amount_mg=220.0,
)


@dataclass
class DayRecord:
    day: int
    intrinsic: float
    adapted: float
    current: float
    fused: float
    alignment_final: float
    alignment_phase: float
    alignment_behavioral: float


def _run_profile(traits: ParticipantPhaseTraits, behavior_for_day, sleep_onset_for_day) -> list:
    """Drive state -> fusion -> alignment for N_DAYS, day by day, using
    only the real engines (no hand-rolled state math)."""

    state = initialize_state(traits.intrinsic_dlmo_hour, traits.chronotype, STATE_CONFIG)
    previous_fused = None
    sleep_onset_window: list = []
    light_window: list = []
    screen_window: list = []
    meal_window: list = []

    records = []
    for day in range(N_DAYS):
        behavior = behavior_for_day(day)
        state, _debug = step(state, behavior, traits, config=STATE_CONFIG)

        dq = DataQualityInput(tier=DataQualityTier.HIGH, window_completeness=1.0)
        fusion_result = fuse(
            xgb_dlmo=None,  # exercise the single-estimator (state-only) fusion path
            state_dlmo=state.current_dlmo_hour,
            previous_fused_dlmo=previous_fused,
            data_quality=dq,
            config=FUSION_CONFIG,
        )
        fused = fusion_result.fused_final
        previous_fused = fused

        onset = sleep_onset_for_day(day)
        sleep_onset_window.append(onset)
        light_window.append(behavior.morning_light_duration_minutes)
        screen_window.append(behavior.evening_screen_duration_hours)
        meal_window.append(behavior.last_meal_hour)
        if len(sleep_onset_window) > 6:
            sleep_onset_window.pop(0)
            light_window.pop(0)
            screen_window.pop(0)
            meal_window.pop(0)

        align_inputs = AlignmentInputs(
            fused_dlmo_hour=fused,
            most_recent_sleep_onset_hour=onset,
            window_sleep_onset_hours=list(sleep_onset_window),
            window_morning_light_duration_minutes=list(light_window),
            window_evening_screen_duration_hours=list(screen_window),
            window_last_meal_hours=list(meal_window),
            window_social_jetlag_minutes=[10.0] * len(sleep_onset_window),
        )
        align_result = compute_alignment(align_inputs, config=ALIGN_CONFIG)

        records.append(DayRecord(
            day=day, intrinsic=state.intrinsic_dlmo_hour, adapted=state.adapted_dlmo_hour,
            current=state.current_dlmo_hour, fused=fused,
            alignment_final=align_result.final_score, alignment_phase=align_result.phase_score,
            alignment_behavioral=align_result.behavioral_score,
        ))
    return records


def _assert_no_nan_inf_and_bounded(records, label):
    for r in records:
        for name, value in [
            ("intrinsic", r.intrinsic), ("adapted", r.adapted), ("current", r.current),
            ("fused", r.fused), ("alignment_final", r.alignment_final),
            ("alignment_phase", r.alignment_phase), ("alignment_behavioral", r.alignment_behavioral),
        ]:
            assert value is not None, f"[{label}] day {r.day}: {name} is None"
            assert math.isfinite(value), f"[{label}] day {r.day}: {name}={value} not finite"
    for r in records:
        assert 0.0 <= r.alignment_final <= 100.0, f"[{label}] day {r.day}: alignment_final out of range: {r.alignment_final}"
        assert 0.0 <= r.alignment_phase <= 100.0, f"[{label}] day {r.day}: alignment_phase out of range"
        assert 0.0 <= r.alignment_behavioral <= 100.0, f"[{label}] day {r.day}: alignment_behavioral out of range"


def _assert_state_bounds(records, intrinsic_hour, label):
    for r in records:
        adapted_dist = abs(circular_diff_hours(r.adapted, intrinsic_hour))
        current_dist = abs(circular_diff_hours(r.current, intrinsic_hour))
        assert adapted_dist <= STATE_CONFIG.adapted_max_offset_hours + 1e-6, f"[{label}] day {r.day}: adapted drifted {adapted_dist}h"
        assert current_dist <= STATE_CONFIG.current_max_offset_hours + 1e-6, f"[{label}] day {r.day}: current drifted {current_dist}h"


def _assert_no_growing_oscillation(values, label, field_name):
    deltas = [abs(a - b) for a, b in zip(values[1:], values[:-1])]
    third = len(deltas) // 3
    first_mean = sum(deltas[:third]) / third
    last_mean = sum(deltas[-third:]) / third
    # Allow generous slack -- this is a smoke check for genuinely
    # exploding oscillation, not a tight numerical bound.
    assert last_mean <= first_mean * 3 + 5.0, (
        f"[{label}] {field_name} day-to-day change amplitude grew: "
        f"first third mean={first_mean}, last third mean={last_mean}"
    )


# --- Profile 1: well-aligned (constant good behavior) ---

def test_well_aligned_profile_180_days_stable():
    traits = ParticipantPhaseTraits(intrinsic_dlmo_hour=21.0, baseline_sleep_onset_hour=23.0, chronotype="Intermediate")
    records = _run_profile(
        traits,
        behavior_for_day=lambda day: WELL_ALIGNED_BEHAVIOR,
        sleep_onset_for_day=lambda day: traits.baseline_sleep_onset_hour,
    )
    _assert_no_nan_inf_and_bounded(records, "well_aligned")
    _assert_state_bounds(records, traits.intrinsic_dlmo_hour, "well_aligned")
    _assert_no_growing_oscillation([r.current for r in records], "well_aligned", "current_dlmo")
    _assert_no_growing_oscillation([r.alignment_final for r in records], "well_aligned", "alignment_final")

    # A consistently well-behaved profile should settle into a high
    # alignment score, not collapse toward 0 (that would indicate a bug,
    # not a real property of "well aligned" synthetic behavior).
    tail_scores = [r.alignment_final for r in records[-20:]]
    assert sum(tail_scores) / len(tail_scores) > 60.0, (
        f"well-aligned profile's alignment score did not settle high: {tail_scores}"
    )


# --- Profile 2: chronically misaligned (constant bad behavior) ---

def test_chronically_misaligned_profile_180_days_stable():
    traits = ParticipantPhaseTraits(intrinsic_dlmo_hour=21.0, baseline_sleep_onset_hour=23.0, chronotype="Intermediate")
    records = _run_profile(
        traits,
        behavior_for_day=lambda day: MISALIGNED_BEHAVIOR,
        sleep_onset_for_day=lambda day: (traits.baseline_sleep_onset_hour + 3.0) % 24.0,
    )
    _assert_no_nan_inf_and_bounded(records, "chronically_misaligned")
    _assert_state_bounds(records, traits.intrinsic_dlmo_hour, "chronically_misaligned")
    _assert_no_growing_oscillation([r.current for r in records], "chronically_misaligned", "current_dlmo")
    _assert_no_growing_oscillation([r.alignment_final for r in records], "chronically_misaligned", "alignment_final")

    # Must not runaway-drift past the documented bound over the full run.
    max_dist = max(abs(circular_diff_hours(r.current, traits.intrinsic_dlmo_hour)) for r in records)
    assert max_dist <= STATE_CONFIG.current_max_offset_hours + 1e-6


# --- Profile 3: improving via intervention (misaligned then corrected) ---

def test_improving_via_intervention_profile_180_days_stable():
    traits = ParticipantPhaseTraits(intrinsic_dlmo_hour=21.0, baseline_sleep_onset_hour=23.0, chronotype="Intermediate")
    switch_day = 60

    def behavior_for_day(day):
        return MISALIGNED_BEHAVIOR if day < switch_day else WELL_ALIGNED_BEHAVIOR

    def sleep_onset_for_day(day):
        if day < switch_day:
            return (traits.baseline_sleep_onset_hour + 3.0) % 24.0
        return traits.baseline_sleep_onset_hour

    records = _run_profile(traits, behavior_for_day, sleep_onset_for_day)
    _assert_no_nan_inf_and_bounded(records, "improving")
    _assert_state_bounds(records, traits.intrinsic_dlmo_hour, "improving")
    _assert_no_growing_oscillation([r.current for r in records], "improving", "current_dlmo")
    _assert_no_growing_oscillation([r.alignment_final for r in records], "improving", "alignment_final")

    # The alignment score in the final stretch (long after the switch to
    # good behavior) should be meaningfully better than right before the
    # switch -- i.e. the system reflects real improvement, not a stuck
    # score. Compare a window just before the switch to the final window.
    pre_switch_scores = [r.alignment_final for r in records[switch_day - 15:switch_day]]
    final_scores = [r.alignment_final for r in records[-15:]]
    pre_mean = sum(pre_switch_scores) / len(pre_switch_scores)
    final_mean = sum(final_scores) / len(final_scores)
    assert final_mean > pre_mean, (
        f"improving profile did not show improvement: pre-switch mean={pre_mean}, final mean={final_mean}"
    )
    # And it should not be pinned exactly at the extremes throughout
    # (a real bug pattern: score stuck at 0 or 100 regardless of input).
    distinct_rounded = {round(s) for s in final_scores}
    assert not (len(distinct_rounded) == 1 and final_scores[0] in (0.0, 100.0)), (
        "alignment score appears pinned at an extreme value"
    )

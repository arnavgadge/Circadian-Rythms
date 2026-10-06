"""Integration tests for the full generator (population -> behavior ->
state -> tables), using a smaller population than the 1,000-participant
production default so the suite stays fast. Counts, distributions, and
bounds are verified at whatever ``num_participants``/``num_days`` each
test actually uses.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SimulationRunConfig
from app.synthetic.simulator import generate_synthetic_dataset
from app.synthetic.validation import run_quality_checks

SMALL_N = 60
DAYS = 30


@pytest.fixture(scope="module")
def small_dataset():
    cfg = SimulationRunConfig(num_participants=SMALL_N, num_days=DAYS, seed=42)
    return generate_synthetic_dataset(cfg, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)


def test_participant_count(small_dataset):
    assert len(small_dataset.participants_df) == SMALL_N


def test_days_per_participant(small_dataset):
    counts = small_dataset.daily_df.groupby("participant_index").size()
    assert (counts == DAYS).all()


def test_daily_row_count(small_dataset):
    assert len(small_dataset.daily_df) == SMALL_N * DAYS


def test_sliding_window_count(small_dataset):
    expected_per_participant = DAYS - 6
    counts = small_dataset.windows_df.groupby("participant_index").size()
    assert (counts == expected_per_participant).all()
    assert len(small_dataset.windows_df) == SMALL_N * expected_per_participant


def test_no_duplicate_participant_date_pairs(small_dataset):
    dupes = small_dataset.daily_df.duplicated(subset=["participant_index", "date"]).sum()
    assert dupes == 0


def test_dlmo_values_are_valid_circular_times(small_dataset):
    for col in ("current_dlmo_hour", "adapted_dlmo_hour", "intrinsic_dlmo_hour"):
        assert (small_dataset.daily_df[col] >= 0.0).all()
        assert (small_dataset.daily_df[col] < 24.0).all()


def test_chronotype_distribution_approximately_matches_configuration(small_dataset):
    counts = small_dataset.participants_df["chronotype"].value_counts(normalize=True)
    expected = DEFAULT_SOURCE_BACKED.chronotype_population_proportions
    for chronotype, proportion in expected.items():
        assert abs(counts.get(chronotype, 0.0) - proportion) < 0.15


def test_personality_distribution_approximately_matches_configuration(small_dataset):
    counts = small_dataset.participants_df["personality_key"].value_counts(normalize=True)
    expected = DEFAULT_SYNTHETIC.personality_proportions
    for personality, proportion in expected.items():
        assert abs(counts.get(personality, 0.0) - proportion) < 0.15


def test_personalities_produce_meaningfully_different_behavior(small_dataset):
    merged = small_dataset.daily_df.merge(
        small_dataset.participants_df[["index", "personality_key"]],
        left_on="participant_index",
        right_on="index",
    )
    screen_by_personality = merged.groupby("personality_key")["evening_screen_duration_hours"].mean()
    # Screen-heavy users must clearly exceed the healthy/stable baseline.
    assert screen_by_personality["screen_heavy_user"] > screen_by_personality["healthy_stable_routine"] + 1.0

    light_by_personality = merged.groupby("personality_key")["morning_light_duration_minutes"].mean()
    assert light_by_personality["healthy_stable_routine"] > light_by_personality["consistent_night_owl"] + 5.0


def test_adapted_and_current_dlmo_remain_bounded(small_dataset):
    from app.synthetic.time_utils import circular_diff_hours

    d_df = small_dataset.daily_df
    current_diffs = [
        abs(circular_diff_hours(c, i))
        for c, i in zip(d_df["current_dlmo_hour"], d_df["intrinsic_dlmo_hour"])
    ]
    adapted_diffs = [
        abs(circular_diff_hours(a, i))
        for a, i in zip(d_df["adapted_dlmo_hour"], d_df["intrinsic_dlmo_hour"])
    ]
    assert max(current_diffs) <= DEFAULT_SYNTHETIC.current_bound_hours_from_intrinsic + 0.05
    assert max(adapted_diffs) <= DEFAULT_SYNTHETIC.adapted_bound_hours_from_intrinsic + 0.05


def test_dlmo_trajectory_does_not_jump_impossibly(small_dataset):
    from app.synthetic.time_utils import circular_diff_hours

    max_jump = 0.0
    for _, group in small_dataset.daily_df.sort_values("day_index").groupby("participant_index"):
        values = group["current_dlmo_hour"].to_numpy()
        for i in range(1, len(values)):
            max_jump = max(max_jump, abs(circular_diff_hours(values[i], values[i - 1])))
    assert max_jump < 3.5  # generous sanity bound; a fresh-random-per-day bug would far exceed this


def test_quality_checks_pass_on_a_freshly_generated_dataset(small_dataset):
    report = run_quality_checks(small_dataset, DEFAULT_SYNTHETIC)
    failed = [c for c in report.checks if not c.passed]
    assert not failed, f"failed checks: {failed}"


def test_same_seed_is_fully_reproducible():
    cfg = SimulationRunConfig(num_participants=25, num_days=DAYS, seed=99)
    a = generate_synthetic_dataset(cfg, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    b = generate_synthetic_dataset(cfg, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)

    pd.testing.assert_frame_equal(
        a.participants_df.drop(columns=[]), b.participants_df.drop(columns=[])
    )
    pd.testing.assert_frame_equal(a.daily_df, b.daily_df)
    pd.testing.assert_frame_equal(a.windows_df, b.windows_df)


def test_different_seeds_produce_different_datasets():
    cfg_a = SimulationRunConfig(num_participants=25, num_days=DAYS, seed=1)
    cfg_b = SimulationRunConfig(num_participants=25, num_days=DAYS, seed=2)
    a = generate_synthetic_dataset(cfg_a, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    b = generate_synthetic_dataset(cfg_b, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)

    assert not a.daily_df["current_dlmo_hour"].equals(b.daily_df["current_dlmo_hour"])


def test_window_dates_never_include_the_target_date_in_the_feature_span(small_dataset):
    windows = small_dataset.windows_df
    assert (windows["feature_end_date"] < windows["target_date"]).all()
    span_days = (windows["feature_end_date"] - windows["feature_start_date"]).apply(lambda td: td.days)
    assert (span_days == 5).all()  # 6 inclusive days = 5 days apart
    gap_days = (windows["target_date"] - windows["feature_end_date"]).apply(lambda td: td.days)
    assert (gap_days == 1).all()  # target is the day immediately after the window

"""Tests for the automated quality-check report."""

from __future__ import annotations

import numpy as np

from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SimulationRunConfig
from app.synthetic.simulator import generate_synthetic_dataset
from app.synthetic.validation import run_quality_checks


def _small_dataset():
    cfg = SimulationRunConfig(num_participants=15, num_days=30, seed=123)
    return generate_synthetic_dataset(cfg, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)


def test_valid_dataset_passes_every_check():
    dataset = _small_dataset()
    report = run_quality_checks(dataset, DEFAULT_SYNTHETIC)
    assert report.ok
    assert len(report.checks) == 16


def test_missing_required_field_is_detected():
    dataset = _small_dataset()
    dataset.daily_df.loc[0, "sleep_onset_hour"] = np.nan

    report = run_quality_checks(dataset, DEFAULT_SYNTHETIC)
    assert not report.ok
    missing_check = next(c for c in report.checks if c.name == "no_missing_required_fields")
    assert not missing_check.passed
    assert "sleep_onset_hour" in missing_check.detail


def test_duplicate_participant_date_pair_is_detected():
    dataset = _small_dataset()
    dataset.daily_df.loc[1, "date"] = dataset.daily_df.loc[0, "date"]
    dataset.daily_df.loc[1, "participant_index"] = dataset.daily_df.loc[0, "participant_index"]

    report = run_quality_checks(dataset, DEFAULT_SYNTHETIC)
    dup_check = next(c for c in report.checks if c.name == "no_duplicate_participant_date_pairs")
    assert not dup_check.passed


def test_out_of_range_dlmo_value_is_detected():
    dataset = _small_dataset()
    dataset.daily_df.loc[0, "current_dlmo_hour"] = 24.5

    report = run_quality_checks(dataset, DEFAULT_SYNTHETIC)
    dlmo_check = next(c for c in report.checks if c.name == "dlmo_values_valid_circular_range")
    assert not dlmo_check.passed


def test_negative_physiological_value_is_detected():
    dataset = _small_dataset()
    dataset.daily_df.loc[0, "resting_hr_bpm"] = -5.0

    report = run_quality_checks(dataset, DEFAULT_SYNTHETIC)
    neg_check = next(c for c in report.checks if c.name == "no_negative_physiological_values")
    assert not neg_check.passed


def test_raise_if_failed_raises_on_a_broken_dataset():
    dataset = _small_dataset()
    dataset.daily_df.loc[0, "evening_screen_duration_hours"] = -1.0
    report = run_quality_checks(dataset, DEFAULT_SYNTHETIC)

    try:
        report.raise_if_failed()
        assert False, "expected AssertionError"
    except AssertionError:
        pass

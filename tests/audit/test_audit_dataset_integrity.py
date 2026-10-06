"""AUDIT 2 -- Dataset integrity (Phase 17 adversarial audit).

Programmatic invariant checks on a freshly generated synthetic dataset
(app.synthetic.simulator.generate_synthetic_dataset), independent of
tests/test_synthetic_dataset.py / tests/test_synthetic_validation.py /
tests/test_synthetic_population.py -- this file targets invariants those
files do not already assert: exact date-coverage per participant (no
gaps, nothing beyond the generation window), participant_id referential
integrity into the written DB, clock-time value ranges, and duration
physical plausibility bounds, all checked at a size close enough to the
documented 1000x30 nominal run to be meaningful while staying fast
enough for the suite (200 participants x 30 days; the windowing
arithmetic itself -- num_days - window_size_days valid windows per
participant -- is verified against the real app.features.windows logic,
not assumed).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.database.models import DailyObservation, Participant, PhysiologyLog
from app.features.windows import compute_valid_windows
from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SimulationRunConfig
from app.synthetic.db_writer import write_dataset_to_db
from app.synthetic.population import CHRONOTYPES
from app.synthetic.personalities import PERSONALITY_PROFILES
from app.synthetic.simulator import generate_synthetic_dataset

N_PARTICIPANTS = 200
N_DAYS = 30
WINDOW_SIZE_DAYS = 6


@pytest.fixture(scope="module")
def audit_dataset():
    cfg = SimulationRunConfig(num_participants=N_PARTICIPANTS, num_days=N_DAYS, seed=1337)
    return generate_synthetic_dataset(cfg, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)


# --------------------------------------------------------------------------
# Row counts / windowing arithmetic
# --------------------------------------------------------------------------


def test_row_count_matches_participants_times_days(audit_dataset):
    assert len(audit_dataset.daily_df) == N_PARTICIPANTS * N_DAYS


def test_window_count_matches_num_days_minus_window_size_per_participant(audit_dataset):
    """Verified against the real app.features.windows logic (not assumed
    arithmetic): num_days - window_size_days valid windows per
    participant (30 - 6 = 24 for the documented nominal run)."""

    start_date = date.fromisoformat(audit_dataset.run_config.start_date_iso)
    dates = [start_date + timedelta(days=i) for i in range(N_DAYS)]
    windows = compute_valid_windows(participant_id=1, available_dates=dates, window_size_days=WINDOW_SIZE_DAYS)
    assert len(windows) == N_DAYS - WINDOW_SIZE_DAYS

    assert len(audit_dataset.windows_df) == N_PARTICIPANTS * (N_DAYS - WINDOW_SIZE_DAYS)


# --------------------------------------------------------------------------
# No duplicate participant/date rows, no gaps, nothing beyond the window
# --------------------------------------------------------------------------


def test_no_duplicated_participant_date_rows(audit_dataset):
    dup_count = audit_dataset.daily_df.duplicated(subset=["participant_index", "date"]).sum()
    assert dup_count == 0


def test_every_participant_has_exactly_the_expected_contiguous_dates(audit_dataset):
    start_date = date.fromisoformat(audit_dataset.run_config.start_date_iso)
    expected_dates = {start_date + timedelta(days=i) for i in range(N_DAYS)}

    for participant_index, group in audit_dataset.daily_df.groupby("participant_index"):
        actual_dates = {d if isinstance(d, date) else d.date() for d in group["date"]}
        assert actual_dates == expected_dates, f"participant {participant_index} has date gaps or extras"


def test_no_dates_beyond_the_generation_window(audit_dataset):
    start_date = date.fromisoformat(audit_dataset.run_config.start_date_iso)
    last_valid_date = start_date + timedelta(days=N_DAYS - 1)

    all_dates = audit_dataset.daily_df["date"].apply(lambda d: d if isinstance(d, date) else d.date())
    assert (all_dates >= start_date).all()
    assert (all_dates <= last_valid_date).all()


# --------------------------------------------------------------------------
# Enumerated / range-bound value checks
# --------------------------------------------------------------------------


def test_chronotype_values_are_within_the_valid_enumerated_set(audit_dataset):
    assert set(audit_dataset.participants_df["chronotype"].unique()) <= set(CHRONOTYPES)


def test_personality_key_values_are_within_the_valid_enumerated_set(audit_dataset):
    valid_keys = set(PERSONALITY_PROFILES.keys())
    assert set(audit_dataset.participants_df["personality_key"].unique()) <= valid_keys


def test_meq_scores_within_instrument_range(audit_dataset):
    scores = audit_dataset.participants_df["meq_score"]
    assert (scores >= DEFAULT_SOURCE_BACKED.meq_score_min).all()
    assert (scores <= DEFAULT_SOURCE_BACKED.meq_score_max).all()


def test_clock_hour_fields_are_within_the_valid_0_to_24_range(audit_dataset):
    """Every *_hour field on daily_df represents a clock-time-derived
    quantity and must be in [0, 24). A malformed clock time (>=24, or
    negative) would silently corrupt every downstream sin/cos encoding
    and clock-time display."""

    hour_columns = [
        c for c in audit_dataset.daily_df.columns
        if c.endswith("_hour") and audit_dataset.daily_df[c].dtype.kind in "fi"
    ]
    assert hour_columns, "expected at least one *_hour column to check"
    for col in hour_columns:
        series = audit_dataset.daily_df[col].dropna()
        if series.empty:
            continue
        assert (series >= 0.0).all(), f"{col} has a negative clock hour"
        assert (series < 24.0).all(), f"{col} has an hour >= 24"


# --------------------------------------------------------------------------
# Behavioral duration physical plausibility
# --------------------------------------------------------------------------


def test_sleep_duration_is_physically_plausible(audit_dataset):
    durations = audit_dataset.daily_df["sleep_duration_hours"]
    assert (durations > 0.0).all()
    assert (durations <= 24.0).all()


def test_duration_minutes_fields_are_never_negative_or_beyond_24h(audit_dataset):
    minutes_columns = [c for c in audit_dataset.daily_df.columns if c.endswith("_duration_minutes")]
    assert minutes_columns
    for col in minutes_columns:
        series = audit_dataset.daily_df[col].dropna()
        if series.empty:
            continue
        assert (series >= 0.0).all(), f"{col} contains a negative duration"
        assert (series <= 24 * 60).all(), f"{col} contains a duration exceeding 24h"


# --------------------------------------------------------------------------
# Referential integrity once written into the relational schema
# --------------------------------------------------------------------------


def test_all_written_daily_observations_reference_a_valid_participant(db_session_factory, audit_dataset):
    from sqlalchemy import select

    write_dataset_to_db(audit_dataset, db_session_factory)

    session = db_session_factory()
    try:
        participant_ids = set(session.execute(select(Participant.id)).scalars().all())
        obs_participant_ids = set(session.execute(select(DailyObservation.participant_id)).scalars().all())
        phys_participant_ids = set(session.execute(select(PhysiologyLog.participant_id)).scalars().all())

        assert obs_participant_ids <= participant_ids
        assert phys_participant_ids <= participant_ids
        assert len(participant_ids) == N_PARTICIPANTS

        obs_count = session.execute(select(DailyObservation)).scalars().all()
        assert len(obs_count) == N_PARTICIPANTS * N_DAYS
    finally:
        session.close()

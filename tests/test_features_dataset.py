"""Tests for the database-backed feature-dataset builder."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import select

from app.database.models import Participant
from app.features.dataset import build_feature_dataset, build_feature_dataset_for_all_participants
from app.features.feature_manifest import TOTAL_FEATURE_COUNT


def test_24_windows_per_participant(small_synthetic_session):
    ids = list(small_synthetic_session.execute(select(Participant.id)).scalars().all())
    dataset = build_feature_dataset(ids, small_synthetic_session)

    counts = dataset.metadata.groupby("participant_id").size()
    assert (counts == 24).all()


def test_database_backed_feature_generation_shape(small_synthetic_session):
    dataset = build_feature_dataset_for_all_participants(small_synthetic_session)

    assert dataset.X.shape == (5 * 24, TOTAL_FEATURE_COUNT)
    assert len(dataset.metadata) == 5 * 24
    assert len(dataset.targets) == 5 * 24
    assert list(dataset.X.columns) == list(dataset.feature_names)


def test_dataset_has_no_missing_values_for_complete_synthetic_data(small_synthetic_session):
    dataset = build_feature_dataset_for_all_participants(small_synthetic_session)
    assert dataset.X.isna().sum().sum() == 0
    assert (dataset.metadata["completeness"] == 1.0).all()


def test_dataset_targets_reference_valid_dlmo_hours(small_synthetic_session):
    dataset = build_feature_dataset_for_all_participants(small_synthetic_session)
    assert dataset.targets["target_dlmo_hour"].notna().all()
    assert (dataset.targets["target_dlmo_hour"] >= 0.0).all()
    assert (dataset.targets["target_dlmo_hour"] < 24.0).all()
    assert dataset.targets["target_dlmo_sin"].between(-1.0, 1.0).all()
    assert dataset.targets["target_dlmo_cos"].between(-1.0, 1.0).all()


def test_metadata_is_traceable_to_participant_and_dates(small_synthetic_session):
    dataset = build_feature_dataset_for_all_participants(small_synthetic_session)
    for col in ("participant_id", "target_date", "window_start", "window_end"):
        assert col in dataset.metadata.columns
        assert dataset.metadata[col].notna().all()


@pytest.mark.skipif(
    os.environ.get("RUN_FULL_SCALE_FEATURE_TEST") != "1",
    reason=(
        "Opt-in: builds the full 1,000-participant x 24-window feature dataset "
        "against the real configured database (requires `python -m "
        "app.scripts.generate_synthetic_data` to have been run first). "
        "Set RUN_FULL_SCALE_FEATURE_TEST=1 to run; takes roughly 1-2 minutes."
    ),
)
def test_full_scale_dataset_is_24000_rows_by_68_features():
    from app.config.settings import load_config
    from app.database.engine import create_app_engine, create_session_factory

    app_config = load_config()
    engine = create_app_engine(app_config)
    session = create_session_factory(engine)()

    participant_count = session.execute(select(Participant.id)).scalars().all()
    if len(participant_count) < 1000:
        pytest.skip("Real database does not contain 1,000 participants yet.")

    dataset = build_feature_dataset_for_all_participants(session)
    session.close()

    assert dataset.X.shape == (24000, 68)

"""Tests for writing generated synthetic data into the Phase 2 schema."""

from __future__ import annotations

from sqlalchemy import func, select

from app.database.engine import create_app_engine, create_session_factory
from app.database.init_db import create_all_tables
from app.database.models import CircadianLabel, DailyObservation, Participant, ParticipantProfile
from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SimulationRunConfig
from app.synthetic.db_writer import reset_all_participants, write_dataset_to_db
from app.synthetic.simulator import generate_synthetic_dataset
from tests.conftest import build_test_config


def _small_dataset(seed=42, n=12):
    cfg = SimulationRunConfig(num_participants=n, num_days=30, seed=seed)
    return generate_synthetic_dataset(cfg, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)


def test_database_insertion_works(db_session_factory):
    dataset = _small_dataset()
    result = write_dataset_to_db(dataset, db_session_factory)

    assert result.participants_written == 12
    assert result.daily_observations_written == 12 * 30
    assert result.circadian_labels_written == 12 * 30

    session = db_session_factory()
    assert session.execute(select(func.count()).select_from(Participant)).scalar_one() == 12
    assert (
        session.execute(select(func.count()).select_from(ParticipantProfile)).scalar_one() == 12
    )
    assert (
        session.execute(select(func.count()).select_from(DailyObservation)).scalar_one() == 12 * 30
    )
    assert (
        session.execute(select(func.count()).select_from(CircadianLabel)).scalar_one() == 12 * 30
    )
    session.close()


def test_ground_truth_labels_are_marked_and_latest(db_session_factory):
    dataset = _small_dataset()
    write_dataset_to_db(dataset, db_session_factory)

    session = db_session_factory()
    labels = session.execute(select(CircadianLabel).limit(5)).scalars().all()
    for label in labels:
        assert label.prediction_status == "synthetic_ground_truth"
        assert label.is_latest is True
        assert label.fused_dlmo_time is not None
        assert label.xgboost_dlmo_time is None  # no model has predicted anything yet
    session.close()


def test_reset_deletes_all_participants_and_cascades(db_session_factory):
    dataset = _small_dataset()
    write_dataset_to_db(dataset, db_session_factory)

    deleted = reset_all_participants(db_session_factory)
    assert deleted == 12

    session = db_session_factory()
    assert session.execute(select(func.count()).select_from(Participant)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(DailyObservation)).scalar_one() == 0
    assert session.execute(select(func.count()).select_from(CircadianLabel)).scalar_one() == 0
    session.close()


def test_regenerated_data_with_same_seed_writes_equivalent_rows(tmp_path):
    config_a = build_test_config(tmp_path, db_filename="a.db")
    config_b = build_test_config(tmp_path, db_filename="b.db")

    engine_a = create_app_engine(config_a)
    engine_b = create_app_engine(config_b)
    create_all_tables(engine_a)
    create_all_tables(engine_b)
    sf_a = create_session_factory(engine_a)
    sf_b = create_session_factory(engine_b)

    dataset_a = _small_dataset(seed=777, n=10)
    dataset_b = _small_dataset(seed=777, n=10)

    write_dataset_to_db(dataset_a, sf_a)
    write_dataset_to_db(dataset_b, sf_b)

    session_a, session_b = sf_a(), sf_b()
    labels_a = session_a.execute(
        select(CircadianLabel.target_date, CircadianLabel.fused_dlmo_time).order_by(
            CircadianLabel.participant_id, CircadianLabel.target_date
        )
    ).all()
    labels_b = session_b.execute(
        select(CircadianLabel.target_date, CircadianLabel.fused_dlmo_time).order_by(
            CircadianLabel.participant_id, CircadianLabel.target_date
        )
    ).all()
    session_a.close()
    session_b.close()

    assert labels_a == labels_b

    engine_a.dispose()
    engine_b.dispose()

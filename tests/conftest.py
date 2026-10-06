"""Shared pytest fixtures for the CircadianIQ database test suite."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import AppConfig
from app.database.engine import create_app_engine, create_session_factory
from app.database.init_db import create_all_tables


def build_test_config(tmp_path: Path, db_filename: str = "test.db") -> AppConfig:
    """Build an AppConfig pointed at an isolated SQLite file under tmp_path."""

    data_dir = tmp_path / "data"
    return AppConfig(
        environment="testing",
        database_url=f"sqlite:///{tmp_path / db_filename}",
        data_dir=data_dir,
        raw_data_dir=data_dir / "raw",
        synthetic_data_dir=data_dir / "synthetic",
        processed_data_dir=data_dir / "processed",
        model_dir=tmp_path / "models",
        log_level="INFO",
    )


@pytest.fixture
def test_config(tmp_path: Path) -> AppConfig:
    return build_test_config(tmp_path)


@pytest.fixture
def engine(test_config: AppConfig) -> Engine:
    """A fresh SQLite engine (file-backed, per test) with FKs enabled."""

    engine = create_app_engine(test_config)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session_factory(engine: Engine) -> sessionmaker[Session]:
    """A session factory bound to ``engine``, with the schema already created."""

    create_all_tables(engine)
    return create_session_factory(engine)


@pytest.fixture
def small_synthetic_dataset(db_session_factory):
    """A small, realistic Phase 3 synthetic dataset (5 participants x 30
    days) written into an isolated per-test database. Reused by Phase 4
    feature-engineering tests so they exercise real generated data
    rather than hand-built fixtures.
    """

    from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SimulationRunConfig
    from app.synthetic.db_writer import write_dataset_to_db
    from app.synthetic.simulator import generate_synthetic_dataset

    cfg = SimulationRunConfig(num_participants=5, num_days=30, seed=42)
    dataset = generate_synthetic_dataset(cfg, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    write_dataset_to_db(dataset, db_session_factory)
    return dataset


@pytest.fixture
def small_synthetic_session(db_session_factory, small_synthetic_dataset):
    session = db_session_factory()
    yield session
    session.close()


@pytest.fixture(scope="module")
def _module_db_session_factory(tmp_path_factory):
    """A module-scoped (shared across tests in one file) isolated database,
    used only by the larger Phase 5 fixture below so the moderately
    expensive 40-participant generation + feature build runs once per
    test module rather than once per test.
    """

    tmp_path = tmp_path_factory.mktemp("phase5_db")
    config = build_test_config(tmp_path)
    engine = create_app_engine(config)
    create_all_tables(engine)
    factory = create_session_factory(engine)
    yield factory
    engine.dispose()


@pytest.fixture(scope="module")
def medium_synthetic_feature_dataset(_module_db_session_factory):
    """A moderately sized Phase 3 synthetic population (40 participants x
    30 days), written to an isolated database and turned into a Phase 4
    feature dataset -- large enough for GroupKFold(n_splits=5) to be
    meaningful, small enough to stay fast. Module-scoped: built once and
    reused by every test in a given Phase 5 test module.
    """

    from app.features.dataset import build_feature_dataset_for_all_participants
    from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SimulationRunConfig
    from app.synthetic.db_writer import write_dataset_to_db
    from app.synthetic.simulator import generate_synthetic_dataset

    cfg = SimulationRunConfig(num_participants=40, num_days=30, seed=42)
    synthetic_dataset = generate_synthetic_dataset(cfg, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    write_dataset_to_db(synthetic_dataset, _module_db_session_factory)

    session = _module_db_session_factory()
    feature_dataset = build_feature_dataset_for_all_participants(session)
    session.close()
    return feature_dataset


@pytest.fixture
def medium_synthetic_session(_module_db_session_factory, medium_synthetic_feature_dataset):
    session = _module_db_session_factory()
    yield session
    session.close()


@pytest.fixture
def api_client(tmp_path: Path, monkeypatch):
    """A ``fastapi.testclient.TestClient`` wired to a fresh, isolated
    SQLite database (via environment variables, exactly how a real
    deployment configures the API) -- never the project's real data
    directory. Each test gets its own schema (created by the app's own
    development-mode lifespan startup)."""

    from fastapi.testclient import TestClient

    db_path = tmp_path / "api_test.db"
    monkeypatch.setenv("CIRCADIANIQ_ENV", "testing")
    monkeypatch.setenv("CIRCADIANIQ_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("CIRCADIANIQ_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CIRCADIANIQ_MODEL_DIR", str(Path(__file__).resolve().parents[1] / "models"))

    from app.api.main import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client

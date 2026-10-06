"""Tests for startup health checks and directory initialization."""

from app.config.settings import AppConfig
from app.health import run_health_check


def _build_test_config(tmp_path) -> AppConfig:
    data_dir = tmp_path / "data"
    return AppConfig(
        environment="testing",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        data_dir=data_dir,
        raw_data_dir=data_dir / "raw",
        synthetic_data_dir=data_dir / "synthetic",
        processed_data_dir=data_dir / "processed",
        model_dir=tmp_path / "models",
        log_level="INFO",
    )


def test_health_check_creates_missing_directories(tmp_path):
    config = _build_test_config(tmp_path)
    for directory in config.required_directories:
        assert not directory.exists()

    result = run_health_check(config)

    assert result.directories_ready
    for directory in config.required_directories:
        assert directory.exists()


def test_health_check_instantiates_database_connection(tmp_path):
    config = _build_test_config(tmp_path)
    result = run_health_check(config)
    assert result.database_ready


def test_health_check_reports_ok_when_all_checks_pass(tmp_path):
    config = _build_test_config(tmp_path)
    result = run_health_check(config)
    assert result.ok

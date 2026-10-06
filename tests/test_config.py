"""Tests for the configuration layer."""

from pathlib import Path

from app.config.settings import AppConfig, load_config


def test_load_config_returns_app_config():
    config = load_config()
    assert isinstance(config, AppConfig)


def test_load_config_defaults_to_development_environment(monkeypatch):
    monkeypatch.delenv("CIRCADIANIQ_ENV", raising=False)
    config = load_config()
    assert config.environment == "development"


def test_load_config_respects_environment_variable(monkeypatch):
    monkeypatch.setenv("CIRCADIANIQ_ENV", "testing")
    config = load_config()
    assert config.environment == "testing"


def test_load_config_paths_are_path_objects():
    config = load_config()
    assert isinstance(config.data_dir, Path)
    assert isinstance(config.model_dir, Path)


def test_required_directories_lists_all_data_paths():
    config = load_config()
    assert config.data_dir in config.required_directories
    assert config.model_dir in config.required_directories

"""Tests for end-to-end artifact persistence + training-run DB logging."""

from __future__ import annotations

from sqlalchemy import select

from app.database.models import TrainingRun
from app.models.config import CVConfig, SplitConfig, TrainingConfig, XGBoostHyperparameters
from app.models.training import persist_training_run, run_training_pipeline

_FAST_HYPERPARAMS = XGBoostHyperparameters(n_estimators=20, max_depth=3, random_state=42)


def test_persist_training_run_saves_artifacts_and_logs_db_row(
    medium_synthetic_feature_dataset, medium_synthetic_session, tmp_path
):
    config = TrainingConfig(
        split=SplitConfig(test_fraction=0.25, split_seed=2025),
        cv=CVConfig(n_splits=5),
        hyperparameters=_FAST_HYPERPARAMS,
    )
    result = run_training_pipeline(medium_synthetic_feature_dataset, medium_synthetic_session, config, compute_shap=False)

    models_dir = tmp_path / "models"
    persisted = persist_training_run(result, models_dir, medium_synthetic_session)

    assert persisted["version"] == 1
    assert persisted["artifact_paths"]["sin_model"].exists()
    assert persisted["artifact_paths"]["cos_model"].exists()
    assert persisted["artifact_paths"]["metadata"].exists()

    run = medium_synthetic_session.get(TrainingRun, persisted["training_run_id"])
    assert run is not None
    assert run.model_type == "xgboost_dlmo"
    assert run.num_participants == result.n_train_participants
    assert run.num_windows == result.n_train_windows
    assert run.feature_count == 68
    assert "test_metrics" in run.cv_metrics
    assert "SYNTHETIC" in run.notes


def test_persist_training_run_never_overwrites_a_previous_version(
    medium_synthetic_feature_dataset, medium_synthetic_session, tmp_path
):
    config = TrainingConfig(
        split=SplitConfig(test_fraction=0.25, split_seed=2025),
        cv=CVConfig(n_splits=5),
        hyperparameters=_FAST_HYPERPARAMS,
    )
    result = run_training_pipeline(medium_synthetic_feature_dataset, medium_synthetic_session, config, compute_shap=False)
    models_dir = tmp_path / "models"

    runs_before = medium_synthetic_session.execute(select(TrainingRun)).scalars().all()

    first = persist_training_run(result, models_dir, medium_synthetic_session)
    second = persist_training_run(result, models_dir, medium_synthetic_session)

    assert first["version"] != second["version"]
    assert first["training_run_id"] != second["training_run_id"]
    assert first["artifact_paths"]["sin_model"].exists()
    assert second["artifact_paths"]["sin_model"].exists()

    runs_after = medium_synthetic_session.execute(select(TrainingRun)).scalars().all()
    assert len(runs_after) == len(runs_before) + 2

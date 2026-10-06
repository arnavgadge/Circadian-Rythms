"""Tests for the training pipeline: GroupKFold integrity, end-to-end
training on a fixture dataset, artifact save/load, and reproducibility.
"""

from __future__ import annotations

import pytest
from sklearn.model_selection import GroupKFold

from app.models.config import CVConfig, SplitConfig, TrainingConfig, XGBoostHyperparameters
from app.models.model_registry import load_model_artifacts, next_version, save_model_artifacts, ModelMetadata
from app.models.sanity import validate_feature_matrix, validate_targets
from app.models.splitting import split_participants
from app.models.training import run_training_pipeline

_FAST_HYPERPARAMS = XGBoostHyperparameters(n_estimators=30, max_depth=3, random_state=42)


def _fast_config(**overrides) -> TrainingConfig:
    return TrainingConfig(
        split=overrides.get("split", SplitConfig(test_fraction=0.25, split_seed=2025)),
        cv=overrides.get("cv", CVConfig(n_splits=5)),
        hyperparameters=overrides.get("hyperparameters", _FAST_HYPERPARAMS),
    )


def test_groupkfold_has_no_participant_overlap_between_folds(medium_synthetic_feature_dataset):
    metadata = medium_synthetic_feature_dataset.metadata
    groups = metadata["participant_id"].to_numpy()
    gkf = GroupKFold(n_splits=5)

    for train_idx, val_idx in gkf.split(metadata, groups=groups):
        train_participants = set(groups[train_idx])
        val_participants = set(groups[val_idx])
        assert train_participants.isdisjoint(val_participants)


def test_feature_sanity_passes_on_valid_dataset(medium_synthetic_feature_dataset):
    validate_feature_matrix(medium_synthetic_feature_dataset.X)


def test_target_sanity_passes_on_valid_dataset(medium_synthetic_feature_dataset):
    validate_targets(medium_synthetic_feature_dataset.targets, medium_synthetic_feature_dataset.metadata)


def test_feature_sanity_detects_wrong_column_count(medium_synthetic_feature_dataset):
    broken = medium_synthetic_feature_dataset.X.drop(columns=[medium_synthetic_feature_dataset.X.columns[0]])
    with pytest.raises(AssertionError):
        validate_feature_matrix(broken)


def test_target_sanity_detects_mismatched_participant_ids(medium_synthetic_feature_dataset):
    targets = medium_synthetic_feature_dataset.targets.copy()
    targets.loc[0, "participant_id"] = -999
    with pytest.raises(AssertionError):
        validate_targets(targets, medium_synthetic_feature_dataset.metadata)


def test_training_pipeline_runs_end_to_end_on_fixture_dataset(medium_synthetic_feature_dataset, medium_synthetic_session):
    config = _fast_config()
    result = run_training_pipeline(medium_synthetic_feature_dataset, medium_synthetic_session, config, compute_shap=False)

    assert result.n_train_participants + result.n_test_participants == 40
    assert result.n_train_participants == 30  # 75% of 40
    assert result.n_test_participants == 10
    assert result.n_train_windows == 30 * 24
    assert result.n_test_windows == 10 * 24
    assert len(result.cv_folds) == 5
    assert result.test_metrics.n == result.n_test_windows
    assert result.success_target_level in ("excellent", "good", "minimum", "below_minimum")


def test_training_pipeline_train_test_participants_never_overlap(medium_synthetic_feature_dataset, medium_synthetic_session):
    config = _fast_config()
    result = run_training_pipeline(medium_synthetic_feature_dataset, medium_synthetic_session, config, compute_shap=False)
    assert set(result.split.train_ids).isdisjoint(set(result.split.test_ids))


def test_personality_and_chronotype_stratified_aggregation_present(medium_synthetic_feature_dataset, medium_synthetic_session):
    config = _fast_config()
    result = run_training_pipeline(medium_synthetic_feature_dataset, medium_synthetic_session, config, compute_shap=False)

    assert len(result.personality_metrics) > 0
    assert set(result.personality_metrics.columns) >= {"group", "n_windows", "mae_minutes", "pct_within_60_min", "bias_minutes"}
    assert len(result.chronotype_metrics) > 0
    assert set(result.chronotype_metrics["group"]).issubset({"Early", "Intermediate", "Late"})


def test_baseline_metrics_are_reported(medium_synthetic_feature_dataset, medium_synthetic_session):
    config = _fast_config()
    result = run_training_pipeline(medium_synthetic_feature_dataset, medium_synthetic_session, config, compute_shap=False)
    assert "participant_mean" in result.baseline_metrics
    assert "msfsc_proxy" in result.baseline_metrics
    assert result.baseline_metrics["participant_mean"]["n"] == result.n_test_windows


def test_reproducibility_same_seed_same_config_gives_equivalent_metrics(medium_synthetic_feature_dataset, medium_synthetic_session):
    config = _fast_config()
    result1 = run_training_pipeline(medium_synthetic_feature_dataset, medium_synthetic_session, config, compute_shap=False)
    result2 = run_training_pipeline(medium_synthetic_feature_dataset, medium_synthetic_session, config, compute_shap=False)

    assert result1.split.train_ids == result2.split.train_ids
    assert result1.split.test_ids == result2.split.test_ids
    assert result1.test_metrics.mae_minutes == pytest.approx(result2.test_metrics.mae_minutes, abs=1e-6)
    assert result1.test_metrics.rmse_minutes == pytest.approx(result2.test_metrics.rmse_minutes, abs=1e-6)


def test_model_artifact_save_and_load_round_trip(medium_synthetic_feature_dataset, medium_synthetic_session, tmp_path):
    config = _fast_config()
    result = run_training_pipeline(medium_synthetic_feature_dataset, medium_synthetic_session, config, compute_shap=False)

    version = next_version(tmp_path)
    assert version == 1

    metadata = ModelMetadata(
        model_version="v1.1",
        model_type="xgboost_dlmo",
        feature_manifest_version="phase4-v1",
        feature_count=68,
        training_date=result.trained_at.isoformat(),
        training_participant_count=result.n_train_participants,
        training_window_count=result.n_train_windows,
        test_participant_count=result.n_test_participants,
        test_window_count=result.n_test_windows,
        hyperparameters=config.hyperparameters.as_xgb_kwargs(),
        split_seed=config.split.split_seed,
        split_version=config.split.split_version,
        cv_metrics=result.cv_summary,
        test_metrics=result.test_metrics.to_dict(),
        baseline_metrics=result.baseline_metrics,
    )
    paths = save_model_artifacts(result.final_model, metadata, tmp_path, version)
    assert paths["sin_model"].exists()
    assert paths["cos_model"].exists()
    assert paths["metadata"].exists()

    loaded_model, loaded_metadata = load_model_artifacts(tmp_path, version, result.final_model.feature_names)
    assert loaded_metadata["feature_count"] == 68
    assert loaded_metadata["training_participant_count"] == result.n_train_participants

    X_sample = medium_synthetic_feature_dataset.X.head(5)
    original_pred = result.final_model.predict_hours(X_sample)
    loaded_pred = loaded_model.predict_hours(X_sample)
    for a, b in zip(original_pred, loaded_pred):
        assert a == pytest.approx(b, abs=1e-9)


def test_next_version_never_reuses_an_existing_version(tmp_path):
    assert next_version(tmp_path) == 1
    (tmp_path / "xgboost_dlmo_sin_v1.pkl").write_text("x")
    assert next_version(tmp_path) == 2
    (tmp_path / "xgboost_dlmo_sin_v5.pkl").write_text("x")
    assert next_version(tmp_path) == 6


def test_save_model_artifacts_refuses_to_overwrite(medium_synthetic_feature_dataset, medium_synthetic_session, tmp_path):
    config = _fast_config()
    result = run_training_pipeline(medium_synthetic_feature_dataset, medium_synthetic_session, config, compute_shap=False)
    metadata = ModelMetadata(
        model_version="v1.1", model_type="xgboost_dlmo", feature_manifest_version="phase4-v1",
        feature_count=68, training_date=result.trained_at.isoformat(),
        training_participant_count=result.n_train_participants, training_window_count=result.n_train_windows,
        test_participant_count=result.n_test_participants, test_window_count=result.n_test_windows,
        hyperparameters={}, split_seed=1, split_version="v1",
        cv_metrics={}, test_metrics={}, baseline_metrics={},
    )
    save_model_artifacts(result.final_model, metadata, tmp_path, 1)
    with pytest.raises(FileExistsError):
        save_model_artifacts(result.final_model, metadata, tmp_path, 1)

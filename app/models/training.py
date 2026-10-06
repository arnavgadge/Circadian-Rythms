"""Training pipeline orchestration.

    DATA PREPARATION -> PARTICIPANT SPLIT -> GROUPED CROSS-VALIDATION
    -> FINAL TRAINING -> HELD-OUT TEST -> REPORTING -> MODEL ARTIFACT

Each stage is a separate, independently testable function; this module
only sequences them. No stage reads the held-out test participants
until the single, final "held-out test" step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
import sklearn
import xgboost
from sklearn.model_selection import GroupKFold
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import TrainingRun
from app.features.dataset import FeatureDataset
from app.models.baselines import predict_baseline_msfsc_proxy, predict_baseline_participant_mean
from app.models.cohorts import attach_participant_cohorts
from app.models.config import DEFAULT_TRAINING_CONFIG, TrainingConfig
from app.models.evaluation import MetricsResult, check_success_targets, compute_metrics, stratified_metrics
from app.models.model_registry import ModelMetadata, next_version, save_model_artifacts
from app.models.sanity import validate_feature_matrix, validate_targets
from app.models.splitting import SplitResult, split_participants
from app.models.xgboost_model import DualComponentXGBModel

COMPLETENESS_BANDS = (
    ("high", 0.95, 1.0 + 1e-9),
    ("moderate", 0.80, 0.95),
    ("low", -1e-9, 0.80),
)


def _completeness_band(completeness: float) -> str:
    for label, low, high in COMPLETENESS_BANDS:
        if low <= completeness < high:
            return label
    return "low"


@dataclass
class CVFoldResult:
    fold_index: int
    n_train_participants: int
    n_val_participants: int
    n_train_windows: int
    n_val_windows: int
    metrics: MetricsResult


@dataclass
class TrainingResult:
    config: TrainingConfig
    split: SplitResult
    cv_folds: list
    cv_summary: dict
    final_model: DualComponentXGBModel
    test_metrics: MetricsResult
    baseline_metrics: dict
    personality_metrics: pd.DataFrame
    chronotype_metrics: pd.DataFrame
    completeness_metrics: pd.DataFrame
    feature_importance_gain: pd.DataFrame
    feature_importance_weight: pd.DataFrame
    shap_importance: Optional[pd.DataFrame]
    success_target_level: str
    test_predictions: pd.DataFrame
    n_train_participants: int
    n_test_participants: int
    n_train_windows: int
    n_test_windows: int
    trained_at: datetime


def _split_dataset(dataset: FeatureDataset, split: SplitResult):
    train_mask = dataset.metadata["participant_id"].isin(split.train_ids).to_numpy()
    test_mask = dataset.metadata["participant_id"].isin(split.test_ids).to_numpy()

    return (
        dataset.X.loc[train_mask].reset_index(drop=True),
        dataset.X.loc[test_mask].reset_index(drop=True),
        dataset.metadata.loc[train_mask].reset_index(drop=True),
        dataset.metadata.loc[test_mask].reset_index(drop=True),
        dataset.targets.loc[train_mask].reset_index(drop=True),
        dataset.targets.loc[test_mask].reset_index(drop=True),
    )


def run_grouped_cross_validation(
    X_train: pd.DataFrame,
    y_sin_train: np.ndarray,
    y_cos_train: np.ndarray,
    hours_train: np.ndarray,
    groups: np.ndarray,
    config: TrainingConfig,
) -> list:
    """5-fold GroupKFold cross-validation within the training participants.

    ``groups`` (one participant ID per row) guarantees every window for a
    participant lands in exactly one fold -- never split across
    train/validation within a fold. Verified by an explicit assertion
    per fold, in addition to the dedicated test suite.
    """

    gkf = GroupKFold(n_splits=config.cv.n_splits)
    fold_results = []

    for fold_index, (train_idx, val_idx) in enumerate(gkf.split(X_train, groups=groups)):
        train_groups = set(groups[train_idx])
        val_groups = set(groups[val_idx])
        assert train_groups.isdisjoint(val_groups), (
            f"GroupKFold fold {fold_index} leaked participants between train and validation"
        )

        fold_model = DualComponentXGBModel.build(config.hyperparameters, tuple(X_train.columns))
        fold_model.fit(
            X_train.iloc[train_idx],
            y_sin_train[train_idx],
            y_cos_train[train_idx],
        )
        predicted_hours = fold_model.predict_hours(X_train.iloc[val_idx])
        metrics = compute_metrics(hours_train[val_idx], predicted_hours)

        fold_results.append(
            CVFoldResult(
                fold_index=fold_index,
                n_train_participants=len(train_groups),
                n_val_participants=len(val_groups),
                n_train_windows=len(train_idx),
                n_val_windows=len(val_idx),
                metrics=metrics,
            )
        )

    return fold_results


def _summarize_cv(fold_results: list) -> dict:
    mae_values = [f.metrics.mae_minutes for f in fold_results]
    rmse_values = [f.metrics.rmse_minutes for f in fold_results]
    pct60_values = [f.metrics.pct_within_60_min for f in fold_results]
    return {
        "n_folds": len(fold_results),
        "mae_minutes_mean": float(np.mean(mae_values)),
        "mae_minutes_std": float(np.std(mae_values)),
        "rmse_minutes_mean": float(np.mean(rmse_values)),
        "rmse_minutes_std": float(np.std(rmse_values)),
        "pct_within_60_min_mean": float(np.mean(pct60_values)),
        "pct_within_60_min_std": float(np.std(pct60_values)),
        "per_fold": [
            {
                "fold_index": f.fold_index,
                "n_train_participants": f.n_train_participants,
                "n_val_participants": f.n_val_participants,
                "n_train_windows": f.n_train_windows,
                "n_val_windows": f.n_val_windows,
                **f.metrics.to_dict(),
            }
            for f in fold_results
        ],
    }


def run_training_pipeline(
    dataset: FeatureDataset,
    session: Session,
    config: TrainingConfig = DEFAULT_TRAINING_CONFIG,
    compute_shap: bool = True,
    shap_sample_size: int = 300,
) -> TrainingResult:
    """Run the full data-prep -> split -> CV -> final-fit -> held-out-test
    -> reporting pipeline. Never touches the test participants before the
    single final evaluation step.
    """

    # --- Data preparation / sanity ---
    validate_feature_matrix(dataset.X)
    validate_targets(dataset.targets, dataset.metadata)

    participant_ids = dataset.metadata["participant_id"].unique().tolist()

    # --- Participant split ---
    split = split_participants(
        participant_ids, config.split.test_fraction, config.split.split_seed, config.split.split_version
    )
    X_train, X_test, meta_train, meta_test, targets_train, targets_test = _split_dataset(dataset, split)

    assert set(meta_train["participant_id"]).isdisjoint(set(meta_test["participant_id"])), (
        "Train/test participant sets overlap -- this must never happen."
    )
    validate_feature_matrix(X_train, X_test)

    y_sin_train = targets_train["target_dlmo_sin"].to_numpy()
    y_cos_train = targets_train["target_dlmo_cos"].to_numpy()
    hours_train = targets_train["target_dlmo_hour"].to_numpy()
    groups_train = meta_train["participant_id"].to_numpy()

    # --- Grouped cross-validation (training participants only) ---
    cv_folds = run_grouped_cross_validation(X_train, y_sin_train, y_cos_train, hours_train, groups_train, config)
    cv_summary = _summarize_cv(cv_folds)

    # --- Final training: fit on ALL 800 training participants ---
    final_model = DualComponentXGBModel.build(config.hyperparameters, tuple(X_train.columns))
    final_model.fit(X_train, y_sin_train, y_cos_train)

    # --- Held-out test: evaluated exactly once ---
    hours_test = targets_test["target_dlmo_hour"].to_numpy()
    predicted_hours_test = final_model.predict_hours(X_test)
    test_metrics = compute_metrics(hours_test, predicted_hours_test)
    success_target_level = check_success_targets(
        test_metrics.mae_minutes, test_metrics.pct_within_60_min, config.success_targets
    )

    # --- Baselines (same held-out test set) ---
    baseline1_hours = predict_baseline_participant_mean(targets_train, meta_test)
    baseline2_hours = predict_baseline_msfsc_proxy(X_test)
    baseline_metrics = {
        "participant_mean": compute_metrics(hours_test, baseline1_hours).to_dict(),
        "msfsc_proxy": compute_metrics(hours_test, baseline2_hours).to_dict(),
    }

    # --- Stratified evaluation ---
    meta_test_cohorts = attach_participant_cohorts(meta_test, session)
    personality_metrics = stratified_metrics(
        hours_test, predicted_hours_test, meta_test_cohorts["personality_key"].to_numpy(),
        meta_test_cohorts["participant_id"].to_numpy(),
    )
    chronotype_metrics = stratified_metrics(
        hours_test, predicted_hours_test, meta_test_cohorts["chronotype"].to_numpy(),
        meta_test_cohorts["participant_id"].to_numpy(),
    )
    completeness_bands = meta_test["completeness"].apply(_completeness_band).to_numpy()
    completeness_metrics = stratified_metrics(
        hours_test, predicted_hours_test, completeness_bands, meta_test["participant_id"].to_numpy()
    )

    # --- Feature importance ---
    feature_importance_gain = final_model.feature_importance("gain")
    feature_importance_weight = final_model.feature_importance("weight")

    shap_importance = None
    if compute_shap:
        shap_importance = _compute_shap_importance(final_model, X_test, shap_sample_size, config.hyperparameters.random_state)

    test_predictions = meta_test_cohorts.copy()
    test_predictions["actual_dlmo_hour"] = hours_test
    test_predictions["predicted_dlmo_hour"] = predicted_hours_test
    test_predictions["completeness_band"] = completeness_bands

    return TrainingResult(
        config=config,
        split=split,
        cv_folds=cv_folds,
        cv_summary=cv_summary,
        final_model=final_model,
        test_metrics=test_metrics,
        baseline_metrics=baseline_metrics,
        personality_metrics=personality_metrics,
        chronotype_metrics=chronotype_metrics,
        completeness_metrics=completeness_metrics,
        feature_importance_gain=feature_importance_gain,
        feature_importance_weight=feature_importance_weight,
        shap_importance=shap_importance,
        success_target_level=success_target_level,
        test_predictions=test_predictions,
        n_train_participants=len(split.train_ids),
        n_test_participants=len(split.test_ids),
        n_train_windows=len(X_train),
        n_test_windows=len(X_test),
        trained_at=datetime.now(timezone.utc),
    )


def _compute_shap_importance(
    model: DualComponentXGBModel, X_test: pd.DataFrame, sample_size: int, seed: int
) -> pd.DataFrame:
    import shap

    sample = X_test.sample(min(sample_size, len(X_test)), random_state=seed)

    sin_explainer = shap.TreeExplainer(model.sin_model)
    cos_explainer = shap.TreeExplainer(model.cos_model)
    sin_shap = np.abs(sin_explainer.shap_values(sample)).mean(axis=0)
    cos_shap = np.abs(cos_explainer.shap_values(sample)).mean(axis=0)

    return pd.DataFrame(
        {
            "feature": sample.columns,
            "sin_mean_abs_shap": sin_shap,
            "cos_mean_abs_shap": cos_shap,
            "mean_abs_shap": (sin_shap + cos_shap) / 2.0,
        }
    ).sort_values("mean_abs_shap", ascending=False).reset_index(drop=True)


def _next_db_model_version_suffix(session: Session, model_type: str, base_version: str) -> int:
    """The next available numeric suffix for ``{base_version}.N`` that is
    globally unique in ``training_runs`` for ``model_type``.

    Computed independently of the models-directory artifact version
    (:func:`app.models.model_registry.next_version`): the database's
    ``(model_type, model_version)`` uniqueness constraint must hold
    regardless of which models directory a given run happened to save
    its files under, so the two counters are deliberately not the same
    thing even though they usually advance together.
    """

    prefix = f"{base_version}."
    existing = session.execute(
        select(TrainingRun.model_version).where(TrainingRun.model_type == model_type)
    ).scalars().all()
    suffixes = [
        int(v[len(prefix):]) for v in existing if v.startswith(prefix) and v[len(prefix):].isdigit()
    ]
    return max(suffixes, default=0) + 1


def persist_training_run(
    result: TrainingResult, models_dir: Path, session: Session
) -> dict:
    """Save versioned model artifacts and log a ``training_runs`` row.

    Never overwrites a previous model version's artifact files (see
    ``app.models.model_registry.next_version``), and never collides with
    a previous ``training_runs`` row's ``model_version`` (see
    :func:`_next_db_model_version_suffix`).
    """

    version = next_version(models_dir)
    db_version_suffix = _next_db_model_version_suffix(session, result.config.model_type, result.config.model_version)
    metadata = ModelMetadata(
        model_version=f"{result.config.model_version}.{db_version_suffix}",
        model_type=result.config.model_type,
        feature_manifest_version="phase4-v1",
        feature_count=len(result.final_model.feature_names),
        training_date=result.trained_at.isoformat(),
        training_participant_count=result.n_train_participants,
        training_window_count=result.n_train_windows,
        test_participant_count=result.n_test_participants,
        test_window_count=result.n_test_windows,
        hyperparameters=result.config.hyperparameters.as_xgb_kwargs(),
        split_seed=result.split.seed,
        split_version=result.split.split_version,
        cv_metrics=result.cv_summary,
        test_metrics=result.test_metrics.to_dict(),
        baseline_metrics=result.baseline_metrics,
        library_versions={
            "xgboost": xgboost.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        notes=(
            "Trained and validated on SYNTHETIC data. Performance does not "
            "demonstrate equivalent performance on real human DLMO data."
        ),
    )

    artifact_paths = save_model_artifacts(result.final_model, metadata, models_dir, version)

    training_run = TrainingRun(
        model_type=result.config.model_type,
        model_version=metadata.model_version,
        num_participants=result.n_train_participants,
        num_windows=result.n_train_windows,
        feature_count=metadata.feature_count,
        cv_metrics={
            "cv_summary": result.cv_summary,
            "test_metrics": result.test_metrics.to_dict(),
            "baseline_metrics": result.baseline_metrics,
            "success_target_level": result.success_target_level,
            "test_participant_count": result.n_test_participants,
            "test_window_count": result.n_test_windows,
            "split_seed": result.split.seed,
            "split_version": result.split.split_version,
        },
        trained_at=result.trained_at,
        artifact_path=str(artifact_paths["metadata"].parent),
        artifact_version=str(version),
        notes=metadata.notes,
    )
    session.add(training_run)
    session.commit()

    return {"version": version, "artifact_paths": artifact_paths, "training_run_id": training_run.id}

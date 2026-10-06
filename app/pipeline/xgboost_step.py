"""STEPS 4-7 of the daily pipeline: build the Phase 4 feature vector
and run the Phase 5 XGBoost model on it.

This module never redefines the feature manifest, the imputation
policy, the model architecture, or the sin/cos decode -- it only calls
``app.features.builder.build_features`` and
``app.models.xgboost_model.DualComponentXGBModel.predict_hours`` (which
itself calls the shared ``app.models.target_encoding.decode_predictions``)
and validates their output shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.features.builder import build_features
from app.features.config import DEFAULT_FEATURE_CONFIG
from app.features.feature_manifest import FEATURE_MANIFEST_VERSION, FEATURE_NAMES, TOTAL_FEATURE_COUNT
from app.models.model_registry import load_model_artifacts
from app.pipeline.config import DEFAULT_PIPELINE_CONFIG, PipelineConfig


@dataclass(frozen=True)
class FeatureStepResult:
    feature_vector: object  # app.features.builder.FeatureVector
    feature_manifest_version: str


@dataclass(frozen=True)
class XgbStepResult:
    xgb_dlmo_hour: float
    predicted_sin: float
    predicted_cos: float
    model_version: int
    model_metadata: dict


def build_feature_step(
    participant_id: int, target_date: date_cls, session: Session
) -> FeatureStepResult:
    """STEP 4. Validates the manifest contract (exactly 68 named
    features matching ``FEATURE_NAMES``) -- never rebuilds features
    itself, only checks what Phase 4 already returned."""

    feature_vector = build_features(participant_id, target_date, session, DEFAULT_FEATURE_CONFIG)

    if feature_vector.feature_names != FEATURE_NAMES:
        raise ValueError("Feature vector's names do not match the locked Phase 4 manifest")
    if len(feature_vector.features) != TOTAL_FEATURE_COUNT:
        raise ValueError(f"Expected {TOTAL_FEATURE_COUNT} features, got {len(feature_vector.features)}")
    if feature_vector.window_end >= target_date:
        raise ValueError("Feature window leaks into the target day")

    return FeatureStepResult(feature_vector=feature_vector, feature_manifest_version=FEATURE_MANIFEST_VERSION)


_loaded_model_cache: dict = {}


def _load_model(models_dir: Path, version: int):
    key = (str(models_dir), version)
    if key not in _loaded_model_cache:
        _loaded_model_cache[key] = load_model_artifacts(models_dir, version, FEATURE_NAMES)
    return _loaded_model_cache[key]


def run_xgboost_step(
    feature_vector,
    models_dir: Path,
    config: PipelineConfig = DEFAULT_PIPELINE_CONFIG,
) -> XgbStepResult:
    """STEPS 5-7: run both regressors and decode the circular
    prediction into a single DLMO hour. Never retrains, never fits --
    ``DualComponentXGBModel.load`` + ``.predict_hours`` only."""

    model, metadata = _load_model(Path(models_dir), config.xgboost_model_version)

    X = pd.DataFrame([feature_vector.features])[list(feature_vector.feature_names)]
    sin_preds, cos_preds = model.predict_sincos(X)
    dlmo_hour = float(model.predict_hours(X)[0])

    return XgbStepResult(
        xgb_dlmo_hour=dlmo_hour,
        predicted_sin=float(sin_preds[0]),
        predicted_cos=float(cos_preds[0]),
        model_version=config.xgboost_model_version,
        model_metadata=metadata,
    )

"""The CircadianIQ DLMO XGBoost model: two independent regressors.

XGBoost 3.x's ``XGBRegressor`` was empirically verified (see
``docs/model_training_and_validation.md`` "Model architecture") to
accept a 2-column target array without raising -- i.e. some native
multi-output support exists in the installed version. This module
deliberately does **not** rely on that: per the brief's explicit
preference for "the simplest reliable implementation" over an
unverified-across-versions native path, it trains two completely
independent ``XGBRegressor`` models (one for ``sin(DLMO)``, one for
``cos(DLMO)``). This also keeps feature importance and SHAP analysis
per-target clean and unambiguous, which a shared multi-output tree
structure would complicate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBRegressor

from app.models.config import XGBoostHyperparameters
from app.models.target_encoding import decode_predictions


@dataclass
class DualComponentXGBModel:
    """Two independent ``XGBRegressor`` models predicting sin(DLMO)/cos(DLMO)."""

    sin_model: XGBRegressor
    cos_model: XGBRegressor
    feature_names: tuple

    @classmethod
    def build(cls, hyperparameters: XGBoostHyperparameters, feature_names: tuple) -> "DualComponentXGBModel":
        kwargs = hyperparameters.as_xgb_kwargs()
        return cls(
            sin_model=XGBRegressor(**kwargs),
            cos_model=XGBRegressor(**kwargs),
            feature_names=tuple(feature_names),
        )

    def _check_columns(self, X: pd.DataFrame) -> None:
        if tuple(X.columns) != self.feature_names:
            raise ValueError(
                "Feature columns do not match the model's expected feature_names "
                "(order and/or membership differ)."
            )

    def fit(self, X: pd.DataFrame, y_sin: np.ndarray, y_cos: np.ndarray) -> "DualComponentXGBModel":
        self._check_columns(X)
        self.sin_model.fit(X, y_sin)
        self.cos_model.fit(X, y_cos)
        return self

    def predict_sincos(self, X: pd.DataFrame) -> tuple:
        self._check_columns(X)
        return self.sin_model.predict(X), self.cos_model.predict(X)

    def predict_hours(self, X: pd.DataFrame) -> np.ndarray:
        sin_pred, cos_pred = self.predict_sincos(X)
        return decode_predictions(sin_pred, cos_pred)

    def feature_importance(self, importance_type: str = "gain") -> pd.DataFrame:
        """Sorted feature importance, averaged across the sin and cos models.

        ``importance_type`` follows XGBoost's own vocabulary: "gain"
        (average gain of splits using the feature -- the primary metric
        requested by the brief), "weight" (number of times a feature is
        used to split), or "cover".
        """

        sin_importance = self.sin_model.get_booster().get_score(importance_type=importance_type)
        cos_importance = self.cos_model.get_booster().get_score(importance_type=importance_type)

        rows = []
        for name in self.feature_names:
            sin_val = sin_importance.get(name, 0.0)
            cos_val = cos_importance.get(name, 0.0)
            rows.append(
                {
                    "feature": name,
                    "sin_importance": sin_val,
                    "cos_importance": cos_val,
                    "mean_importance": (sin_val + cos_val) / 2.0,
                }
            )
        return pd.DataFrame(rows).sort_values("mean_importance", ascending=False).reset_index(drop=True)

    def save(self, sin_path: Path, cos_path: Path) -> None:
        joblib.dump(self.sin_model, sin_path)
        joblib.dump(self.cos_model, cos_path)

    @classmethod
    def load(cls, sin_path: Path, cos_path: Path, feature_names: tuple) -> "DualComponentXGBModel":
        return cls(
            sin_model=joblib.load(sin_path),
            cos_model=joblib.load(cos_path),
            feature_names=tuple(feature_names),
        )

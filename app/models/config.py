"""Configuration for the CircadianIQ XGBoost training + validation pipeline.

Every hyperparameter, split setting, and CV setting lives here, in one
place -- never scattered as bare literals through the training code.
The hyperparameter defaults below are the project brief's own
"engineering starting points", explicitly **not** claimed to be
scientifically optimal; hyperparameter search is out of scope for this
phase (see ``docs/model_training_and_validation.md``).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SplitConfig:
    """Participant-level train/test split configuration."""

    test_fraction: float = 0.2  # 1,000 participants -> 800 train / 200 test
    split_seed: int = 2025
    split_version: str = "v1"


@dataclass(frozen=True)
class CVConfig:
    """Grouped cross-validation configuration (within the training participants)."""

    n_splits: int = 5
    # GroupKFold itself is deterministic given a fixed group/row order; no
    # separate shuffle seed exists for it (unlike KFold). Row order is
    # fixed by how the feature dataset was built, which is itself
    # deterministic (see Phase 4).


@dataclass(frozen=True)
class XGBoostHyperparameters:
    """Baseline XGBoost hyperparameters -- engineering starting points,
    not scientifically optimal values. See project brief "MODEL" section.
    """

    n_estimators: int = 500
    max_depth: int = 6
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    random_state: int = 42
    objective: str = "reg:squarederror"
    n_jobs: int = -1

    def as_xgb_kwargs(self) -> dict:
        return {
            "n_estimators": self.n_estimators,
            "max_depth": self.max_depth,
            "learning_rate": self.learning_rate,
            "subsample": self.subsample,
            "colsample_bytree": self.colsample_bytree,
            "random_state": self.random_state,
            "objective": self.objective,
            "n_jobs": self.n_jobs,
        }


@dataclass(frozen=True)
class SuccessTargets:
    """Project success targets -- targets, not guarantees (see brief)."""

    minimum_mae_minutes: float = 60.0
    minimum_pct_within_60: float = 70.0
    good_mae_minutes: float = 45.0
    good_pct_within_60: float = 80.0
    excellent_mae_minutes: float = 35.0
    excellent_pct_within_60: float = 85.0


@dataclass(frozen=True)
class TrainingConfig:
    """Top-level configuration for one training run."""

    model_version: str = "v1"
    model_type: str = "xgboost_dlmo"
    config_version: str = "1.0.0"

    split: SplitConfig = field(default_factory=SplitConfig)
    cv: CVConfig = field(default_factory=CVConfig)
    hyperparameters: XGBoostHyperparameters = field(default_factory=XGBoostHyperparameters)
    success_targets: SuccessTargets = field(default_factory=SuccessTargets)

    error_bands_minutes: tuple = (15.0, 30.0, 60.0, 90.0)


DEFAULT_TRAINING_CONFIG = TrainingConfig()

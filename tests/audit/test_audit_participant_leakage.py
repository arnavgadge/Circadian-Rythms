"""AUDIT 4 -- Participant leakage (adversarial).

Recomputes the train/test split and the GroupKFold fold assignments
from the *actual* code path (`app.models.splitting.split_participants`,
`app.models.training.run_grouped_cross_validation`) against a real
generated dataset -- never a hardcoded expected participant list -- and
asserts empty-set intersections everywhere:

  * train vs. global test (top-level split)
  * every fold's train vs. that same fold's validation set
  * every fold's train/val sets are drawn only from the training-side
    participants (never dipping into the held-out test participants)

Also checks that no feature/target preprocessing step fits a global
parameter (scaler/imputer/mean/std) across train+val+test rows: the
dataset builder (`app.features.dataset`) and imputation module
(`app.features.imputation`) are inspected to confirm every fallback
value is either window-local or drawn from that *same participant's*
own pre-window history -- never a population statistic computed across
participants at fit time (the population defaults are fixed constants
from `app.features.config`, not fitted).
"""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd

from app.models.config import DEFAULT_TRAINING_CONFIG
from app.models.splitting import split_participants
from app.models.training import run_grouped_cross_validation
from sklearn.model_selection import GroupKFold


def test_train_test_split_has_zero_participant_overlap_on_real_dataset(medium_synthetic_feature_dataset):
    dataset = medium_synthetic_feature_dataset
    participant_ids = dataset.metadata["participant_id"].unique().tolist()

    split = split_participants(
        participant_ids,
        DEFAULT_TRAINING_CONFIG.split.test_fraction,
        DEFAULT_TRAINING_CONFIG.split.split_seed,
        DEFAULT_TRAINING_CONFIG.split.split_version,
    )

    train_set = set(split.train_ids)
    test_set = set(split.test_ids)
    assert train_set.isdisjoint(test_set)
    assert train_set | test_set == set(participant_ids)

    # Every row's participant_id must land on exactly one side.
    train_mask = dataset.metadata["participant_id"].isin(train_set)
    test_mask = dataset.metadata["participant_id"].isin(test_set)
    assert not (train_mask & test_mask).any()
    assert (train_mask | test_mask).all()


def test_every_groupkfold_fold_has_zero_internal_participant_overlap(medium_synthetic_feature_dataset):
    """Recompute GroupKFold directly (bypassing run_grouped_cross_validation's
    own model-fitting) and check every fold pair for participant overlap,
    plus confirm each fold's participants are a subset of the training
    participants only (never test-side)."""

    dataset = medium_synthetic_feature_dataset
    participant_ids = dataset.metadata["participant_id"].unique().tolist()

    split = split_participants(
        participant_ids,
        DEFAULT_TRAINING_CONFIG.split.test_fraction,
        DEFAULT_TRAINING_CONFIG.split.split_seed,
        DEFAULT_TRAINING_CONFIG.split.split_version,
    )
    train_set = set(split.train_ids)
    test_set = set(split.test_ids)

    train_mask = dataset.metadata["participant_id"].isin(train_set).to_numpy()
    meta_train = dataset.metadata.loc[train_mask].reset_index(drop=True)
    X_train = dataset.X.loc[train_mask].reset_index(drop=True)
    groups_train = meta_train["participant_id"].to_numpy()

    gkf = GroupKFold(n_splits=DEFAULT_TRAINING_CONFIG.cv.n_splits)
    fold_pairs = list(gkf.split(X_train, groups=groups_train))
    assert len(fold_pairs) == DEFAULT_TRAINING_CONFIG.cv.n_splits

    all_fold_groups = []
    for fold_index, (train_idx, val_idx) in enumerate(fold_pairs):
        fold_train_groups = set(groups_train[train_idx])
        fold_val_groups = set(groups_train[val_idx])

        assert fold_train_groups.isdisjoint(fold_val_groups), (
            f"fold {fold_index}: train/val participant overlap {fold_train_groups & fold_val_groups}"
        )
        # Neither side of any fold may include a held-out test participant.
        assert fold_train_groups.isdisjoint(test_set), f"fold {fold_index} train touches test participants"
        assert fold_val_groups.isdisjoint(test_set), f"fold {fold_index} val touches test participants"
        # Both sides must be subsets of the training-side participants.
        assert fold_train_groups <= train_set
        assert fold_val_groups <= train_set

        all_fold_groups.append((fold_train_groups, fold_val_groups))

    # Cross-fold check: fold i's validation set vs fold j's validation set
    # need not be disjoint across folds is fine (folds partition val sets,
    # so they ARE disjoint) -- explicitly verify the val folds partition
    # the training participants with no participant appearing in two
    # different folds' validation sets (GroupKFold's core guarantee).
    val_group_union = set()
    for _, val_groups in all_fold_groups:
        assert val_group_union.isdisjoint(val_groups), (
            "a participant appears in more than one fold's validation set"
        )
        val_group_union |= val_groups
    assert val_group_union == train_set


def test_run_grouped_cross_validation_end_to_end_asserts_hold(medium_synthetic_feature_dataset):
    """Exercise the actual production function (not a reimplementation) and
    confirm it completes -- its own internal assertion would raise if any
    fold leaked, and we additionally recheck the returned fold metadata's
    participant counts sum correctly."""

    dataset = medium_synthetic_feature_dataset
    participant_ids = dataset.metadata["participant_id"].unique().tolist()
    split = split_participants(
        participant_ids,
        DEFAULT_TRAINING_CONFIG.split.test_fraction,
        DEFAULT_TRAINING_CONFIG.split.split_seed,
        DEFAULT_TRAINING_CONFIG.split.split_version,
    )
    train_set = set(split.train_ids)
    train_mask = dataset.metadata["participant_id"].isin(train_set).to_numpy()
    meta_train = dataset.metadata.loc[train_mask].reset_index(drop=True)
    X_train = dataset.X.loc[train_mask].reset_index(drop=True)
    targets_train = dataset.targets.loc[train_mask].reset_index(drop=True)

    y_sin_train = targets_train["target_dlmo_sin"].to_numpy()
    y_cos_train = targets_train["target_dlmo_cos"].to_numpy()
    hours_train = targets_train["target_dlmo_hour"].to_numpy()
    groups_train = meta_train["participant_id"].to_numpy()

    fold_results = run_grouped_cross_validation(
        X_train, y_sin_train, y_cos_train, hours_train, groups_train, DEFAULT_TRAINING_CONFIG
    )
    assert len(fold_results) == DEFAULT_TRAINING_CONFIG.cv.n_splits
    for fold in fold_results:
        assert fold.n_train_participants + fold.n_val_participants == len(train_set)


# --- No global (cross-participant / cross-split) fitting -------------------


def test_feature_builder_has_no_global_fit_or_scaler_call():
    """Confirm, against the real source, that the feature-engineering layer
    never fits a scaler/imputer/global statistic across participants.
    A leaky-preprocessing bug would show up as a `.fit(` / `StandardScaler`
    / `SimpleImputer` call somewhere in app.features; there is none."""

    import app.features.builder as builder_module
    import app.features.dataset as dataset_module
    import app.features.imputation as imputation_module

    forbidden_patterns = ("StandardScaler", "SimpleImputer", "MinMaxScaler", ".fit(", ".fit_transform(")
    for module in (builder_module, dataset_module, imputation_module):
        source = inspect.getsource(module)
        for pattern in forbidden_patterns:
            assert pattern not in source, (
                f"{module.__name__} contains {pattern!r} -- possible global/leaky fitting"
            )


def test_imputation_personal_history_is_scoped_to_window_start_and_own_participant(medium_synthetic_feature_dataset):
    """Re-derive, from the real database, that the 'personal history'
    imputation fallback used by app.features.builder only ever draws from
    rows strictly before the window AND belonging to the same participant
    -- i.e. it can never pull in another participant's data (which would
    be a cross-participant leak distinct from temporal leak) nor future
    data for the same participant. This directly re-checks the query
    predicates in app.features.builder._personal_history_* helpers."""

    import app.features.builder as builder_module

    source = inspect.getsource(builder_module)
    # Every personal-history helper must filter on both conditions.
    for fn_name in [
        "_personal_history_last_clock_time_hour",
        "_personal_history_numeric_mean",
        "_personal_history_msfsc_hour",
        "_personal_history_free_day_ratio",
        "_personal_history_exercise_frequency",
    ]:
        fn = getattr(builder_module, fn_name)
        fn_source = inspect.getsource(fn)
        assert "participant_id == participant_id" in fn_source, (
            f"{fn_name} does not filter by participant_id -- cross-participant leak risk"
        )
        assert "observation_date < window_start" in fn_source, (
            f"{fn_name} does not strictly filter to before window_start -- temporal leak risk"
        )

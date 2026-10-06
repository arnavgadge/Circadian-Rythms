"""Pre-training feature/target sanity checks.

Fails loudly (``AssertionError``) rather than silently dropping rows
or proceeding with a corrupted dataset -- per the brief, invalid rows
must be reported and training stopped unless a documented cleaning
policy exists (none does, for this phase).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.features.feature_manifest import FEATURE_NAMES, TOTAL_FEATURE_COUNT

_FORBIDDEN_PATTERNS = (
    "sleep_onset",
    "sleep_offset",
    "sleep_midpoint_sin",
    "sleep_midpoint_cos",
    "weighted_sleep_onset",
    "resting_hr",
    "hrv",
    "wrist_temp",
    "target",
)


def validate_feature_matrix(X: pd.DataFrame, X_other: pd.DataFrame | None = None) -> None:
    """Validate a feature matrix (checks 1-2, 4-10 of the brief's "FEATURE
    SANITY" list). Pass ``X_other`` (e.g. the test matrix, when validating
    the training matrix) to also check #3, identical columns.
    """

    errors = []

    # 1. exactly 68 features
    if X.shape[1] != TOTAL_FEATURE_COUNT:
        errors.append(f"expected {TOTAL_FEATURE_COUNT} feature columns, got {X.shape[1]}")

    # 2. feature names match the Phase 4 manifest exactly (order included)
    if tuple(X.columns) != FEATURE_NAMES:
        errors.append("feature column names/order do not match app.features.feature_manifest.FEATURE_NAMES")

    # 3. train/test feature columns identical
    if X_other is not None and tuple(X.columns) != tuple(X_other.columns):
        errors.append("the two feature matrices being compared do not have identical columns")

    # 4, 5, 6, 7: forbidden / target / physiology columns
    forbidden_hits = [
        col for col in X.columns for pattern in _FORBIDDEN_PATTERNS if pattern in col
    ]
    if forbidden_hits:
        errors.append(f"forbidden columns present: {forbidden_hits}")

    # 8. no NaN
    nan_columns = X.columns[X.isna().any()].tolist()
    if nan_columns:
        errors.append(f"NaN values present in columns: {nan_columns}")

    # 9. no infinity
    numeric_X = X.select_dtypes(include=[np.number])
    inf_columns = numeric_X.columns[np.isinf(numeric_X.to_numpy()).any(axis=0)].tolist()
    if inf_columns:
        errors.append(f"infinite values present in columns: {inf_columns}")

    # 10. numeric dtypes are valid
    non_numeric = [col for col in X.columns if not pd.api.types.is_numeric_dtype(X[col])]
    if non_numeric:
        errors.append(f"non-numeric dtype columns: {non_numeric}")

    if errors:
        raise AssertionError("Feature matrix failed sanity checks: " + "; ".join(errors))


def validate_targets(targets: pd.DataFrame, metadata: pd.DataFrame) -> None:
    """Validate the target-reference dataframe (the brief's "TARGET SANITY" list)."""

    errors = []

    # 4. no missing target values
    if targets[["target_dlmo_hour", "target_dlmo_sin", "target_dlmo_cos"]].isna().any().any():
        errors.append("missing values found in target_dlmo_hour/target_dlmo_sin/target_dlmo_cos")

    # 1. sin/cos targets are finite
    sincos = targets[["target_dlmo_sin", "target_dlmo_cos"]].to_numpy(dtype=float)
    if not np.all(np.isfinite(sincos)):
        errors.append("non-finite values found in target_dlmo_sin/target_dlmo_cos")

    # 2. target clock times are valid ([0, 24))
    hours = targets["target_dlmo_hour"].to_numpy(dtype=float)
    if not np.all((hours >= 0.0) & (hours < 24.0)):
        errors.append("target_dlmo_hour values found outside [0, 24)")

    # 3. target vectors have sensible magnitude (should be ~1, since they
    # are the exact encoding of a real hour, not a model prediction)
    magnitudes = np.sqrt(sincos[:, 0] ** 2 + sincos[:, 1] ** 2)
    if not np.all(np.abs(magnitudes - 1.0) < 1e-6):
        bad = int(np.sum(np.abs(magnitudes - 1.0) >= 1e-6))
        errors.append(f"{bad} target sin/cos vectors have magnitude far from 1.0")

    # 5. target participant IDs (and dates) match feature rows
    if len(targets) != len(metadata):
        errors.append(f"targets has {len(targets)} rows but metadata has {len(metadata)} rows")
    else:
        mismatched_participants = int(
            (targets["participant_id"].to_numpy() != metadata["participant_id"].to_numpy()).sum()
        )
        mismatched_dates = int(
            (targets["target_date"].to_numpy() != metadata["target_date"].to_numpy()).sum()
        )
        if mismatched_participants:
            errors.append(f"{mismatched_participants} rows have mismatched participant_id between targets and metadata")
        if mismatched_dates:
            errors.append(f"{mismatched_dates} rows have mismatched target_date between targets and metadata")

    if errors:
        raise AssertionError("Targets failed sanity checks: " + "; ".join(errors))

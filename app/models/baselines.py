"""Simple, non-learned baselines to compare XGBoost against.

Per the brief, XGBoost must never be evaluated in isolation, and a
baseline must respect exactly the information the model itself is
allowed to use -- so neither baseline touches sleep onset/offset, and
neither touches physiology.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.models.target_encoding import decode_predictions
from app.synthetic.time_utils import circular_mean_hours


def predict_baseline_participant_mean(
    train_targets: pd.DataFrame, test_metadata: pd.DataFrame
) -> np.ndarray:
    """Baseline 1: predict each test participant's mean *training-target*
    DLMO (the circular mean of that participant's target DLMO values
    observed in the training windows).

    For a participant with no training-window history at all (not
    expected under the participant-level split, since every training
    participant contributes 24 training windows), falls back to the
    overall training-set circular mean DLMO.
    """

    per_participant_hours: dict = {}
    for participant_id, sub in train_targets.groupby("participant_id"):
        hours = sub["target_dlmo_hour"].dropna().to_numpy()
        if len(hours) > 0:
            per_participant_hours[participant_id] = circular_mean_hours(hours)

    overall_mean = circular_mean_hours(train_targets["target_dlmo_hour"].dropna().to_numpy())

    return np.array(
        [per_participant_hours.get(pid, overall_mean) for pid in test_metadata["participant_id"]],
        dtype=float,
    )


def predict_baseline_msfsc_proxy(X: pd.DataFrame) -> np.ndarray:
    """Baseline 2: a naive, non-learned phase-proxy prediction, decoded
    directly from each row's own ``msfsc_sin``/``msfsc_cos`` features.

    MSFsc (corrected free-day sleep midpoint) is the one phase-proxy
    signal the Phase 4 feature architecture explicitly sanctions as
    *not* being direct sleep-onset timing (see
    ``docs/synthetic_data_generation.md`` / ``docs/feature_engineering.md``
    "anti-circularity"), which is why it is used here rather than any
    sleep-timing feature: using sleep onset as a baseline would violate
    the same anti-circularity rule the model itself is built to respect.
    This baseline requires no learned parameters -- it simply reads an
    already-computed feature back out and treats it as a naive DLMO guess.
    """

    return decode_predictions(X["msfsc_sin"].to_numpy(), X["msfsc_cos"].to_numpy())

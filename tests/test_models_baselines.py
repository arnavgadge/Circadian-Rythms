"""Tests for the non-learned baseline predictors."""

from __future__ import annotations

import pandas as pd
import pytest

from app.features.time_encoding import clock_to_sincos
from app.models.baselines import predict_baseline_msfsc_proxy, predict_baseline_participant_mean


def test_baseline_participant_mean_uses_that_participants_training_history():
    train_targets = pd.DataFrame(
        {
            "participant_id": [1, 1, 1, 2, 2, 2],
            "target_dlmo_hour": [22.0, 22.0, 22.0, 6.0, 6.0, 6.0],
        }
    )
    test_metadata = pd.DataFrame({"participant_id": [1, 2]})

    predictions = predict_baseline_participant_mean(train_targets, test_metadata)
    assert predictions[0] == pytest.approx(22.0, abs=1e-6)
    assert predictions[1] == pytest.approx(6.0, abs=1e-6)


def test_baseline_participant_mean_falls_back_for_unknown_participant():
    train_targets = pd.DataFrame({"participant_id": [1, 1], "target_dlmo_hour": [22.0, 22.0]})
    test_metadata = pd.DataFrame({"participant_id": [999]})  # not in training history

    predictions = predict_baseline_participant_mean(train_targets, test_metadata)
    assert predictions[0] == pytest.approx(22.0, abs=1e-6)  # falls back to overall mean


def test_baseline_participant_mean_uses_circular_averaging():
    # 23:00 and 01:00 should average to 00:00, not 12:00.
    train_targets = pd.DataFrame({"participant_id": [1, 1], "target_dlmo_hour": [23.0, 1.0]})
    test_metadata = pd.DataFrame({"participant_id": [1]})

    predictions = predict_baseline_participant_mean(train_targets, test_metadata)
    assert predictions[0] == pytest.approx(0.0, abs=1e-6) or predictions[0] == pytest.approx(24.0, abs=1e-6)


def test_baseline_msfsc_proxy_decodes_the_msfsc_feature_directly():
    sin_v, cos_v = clock_to_sincos(4.5)
    X = pd.DataFrame({"msfsc_sin": [sin_v], "msfsc_cos": [cos_v]})
    predictions = predict_baseline_msfsc_proxy(X)
    assert predictions[0] == pytest.approx(4.5, abs=1e-6)


def test_baseline_msfsc_proxy_does_not_touch_sleep_onset_columns():
    import inspect

    from app.models import baselines

    source = inspect.getsource(baselines)
    assert "sleep_onset" not in source
    assert "sleep_offset" not in source

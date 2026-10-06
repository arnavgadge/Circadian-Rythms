"""Tests for target circular encoding/decoding, including the
predicted-vector normalization step."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.models.target_encoding import clock_to_sincos, decode_predictions, normalize_sincos


def test_normalize_sincos_leaves_unit_vector_unchanged():
    sin_v, cos_v = clock_to_sincos(14.5)
    n_sin, n_cos = normalize_sincos(sin_v, cos_v)
    assert n_sin == pytest.approx(sin_v)
    assert n_cos == pytest.approx(cos_v)


def test_normalize_sincos_rescales_off_circle_vector():
    n_sin, n_cos = normalize_sincos(0.6, 0.8)  # magnitude already 1
    assert math.hypot(n_sin, n_cos) == pytest.approx(1.0)

    n_sin2, n_cos2 = normalize_sincos(3.0, 4.0)  # magnitude 5
    assert math.hypot(n_sin2, n_cos2) == pytest.approx(1.0)
    assert n_sin2 == pytest.approx(0.6)
    assert n_cos2 == pytest.approx(0.8)


def test_normalize_sincos_handles_zero_vector():
    assert normalize_sincos(0.0, 0.0) == (0.0, 0.0)


def test_decode_predictions_matches_true_encoding_for_unit_vectors():
    true_hours = np.array([0.0, 6.0, 12.0, 18.0, 23.5])
    sins, coss = zip(*[clock_to_sincos(h) for h in true_hours])
    decoded = decode_predictions(np.array(sins), np.array(coss))
    for true_h, decoded_h in zip(true_hours, decoded):
        assert decoded_h == pytest.approx(true_h, abs=1e-6)


def test_decode_predictions_handles_off_circle_magnitude():
    """A raw model prediction rarely lands exactly on the unit circle;
    decoding must still recover the correct angle regardless of magnitude."""

    true_sin, true_cos = clock_to_sincos(21.25)
    scaled_sin, scaled_cos = true_sin * 2.5, true_cos * 2.5  # magnitude 2.5, not 1
    decoded = decode_predictions(np.array([scaled_sin]), np.array([scaled_cos]))
    assert decoded[0] == pytest.approx(21.25, abs=1e-6)


def test_decode_predictions_handles_shrunk_magnitude():
    true_sin, true_cos = clock_to_sincos(3.75)
    shrunk_sin, shrunk_cos = true_sin * 0.1, true_cos * 0.1
    decoded = decode_predictions(np.array([shrunk_sin]), np.array([shrunk_cos]))
    assert decoded[0] == pytest.approx(3.75, abs=1e-4)


def test_decode_predictions_output_always_in_valid_range():
    rng = np.random.default_rng(0)
    sins = rng.uniform(-3, 3, size=200)
    coss = rng.uniform(-3, 3, size=200)
    decoded = decode_predictions(sins, coss)
    assert np.all(decoded >= 0.0)
    assert np.all(decoded < 24.0)


def test_decode_predictions_zero_vector_does_not_raise():
    decoded = decode_predictions(np.array([0.0]), np.array([0.0]))
    assert decoded[0] == 0.0

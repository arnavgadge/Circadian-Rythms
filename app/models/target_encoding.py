"""Target circular encoding/decoding for the XGBoost DLMO model.

Encoding a true clock hour is exactly the Phase 4 utility
(:func:`app.features.time_encoding.clock_to_sincos`) -- re-exported
here so training code has one obvious import. **Decoding a model's
predicted** ``(sin, cos)`` pair is different from decoding a true
encoded value: nothing constrains the two regressors' raw outputs to
lie exactly on the unit circle, so the predicted vector must be
re-normalized before ``atan2`` is used to recover an hour. Skipping
this step would silently bias the decoded hour whenever the predicted
magnitude drifts from 1 (which it always does, at least slightly).
"""

from __future__ import annotations

import math

import numpy as np

from app.features.time_encoding import clock_to_sincos, sincos_to_clock

__all__ = ["clock_to_sincos", "sincos_to_clock", "normalize_sincos", "decode_predictions"]


def normalize_sincos(sin_val: float, cos_val: float) -> tuple:
    """Project a possibly off-circle ``(sin, cos)`` pair back onto the unit circle.

    ``r = sqrt(sin^2 + cos^2)``; if ``r > 0``, divide both components by
    ``r``. If ``r == 0`` (a degenerate all-zero prediction), the angle is
    undefined -- returned unchanged (0.0, 0.0), and the caller
    (:func:`decode_predictions`) falls back to hour 0.0 for that row
    rather than dividing by zero.
    """

    r = math.hypot(sin_val, cos_val)
    if r > 0:
        return sin_val / r, cos_val / r
    return 0.0, 0.0


def decode_predictions(sin_preds: np.ndarray, cos_preds: np.ndarray) -> np.ndarray:
    """Decode an array of raw (possibly off-circle) predicted ``(sin, cos)``
    pairs into clock hours in ``[0, 24)``.

    Vectorized equivalent of, per row: normalize via
    :func:`normalize_sincos`, then ``atan2(sin_norm, cos_norm)`` -> hour.
    """

    sin_preds = np.asarray(sin_preds, dtype=float)
    cos_preds = np.asarray(cos_preds, dtype=float)

    r = np.sqrt(sin_preds**2 + cos_preds**2)
    safe_r = np.where(r > 0, r, 1.0)  # avoid division by zero; result overridden below
    sin_norm = sin_preds / safe_r
    cos_norm = cos_preds / safe_r

    angle = np.arctan2(sin_norm, cos_norm)
    angle = np.where(angle < 0, angle + 2 * np.pi, angle)
    hours = angle / (2 * np.pi) * 24.0

    # Degenerate r == 0 rows: angle is undefined: define as hour 0.0.
    hours = np.where(r > 0, hours, 0.0)
    return hours

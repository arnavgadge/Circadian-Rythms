"""Circular-time fusion: the only correct way to combine two clock times.

Never average clock hours directly (``(23.8 + 0.2) / 2`` is
biologically meaningless, landing near noon for two estimates that are
both near midnight). Every combination here goes through a weighted
sum of unit circular vectors, normalized, then decoded back to an hour
-- reusing the same primitives already established in Phases 4/5
(:mod:`app.features.time_encoding`, :mod:`app.models.target_encoding`)
rather than reimplementing sin/cos encoding a third time.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from app.features.time_encoding import clock_to_sincos
from app.fusion.config import DEFAULT_FUSION_CONFIG, FusionConfig
from app.fusion.weights import FusionWeights
from app.models.target_encoding import sincos_to_clock


@dataclass(frozen=True)
class CircularFusionResult:
    fused_hour: Optional[float]
    vector_magnitude: float
    used_fallback: bool
    fallback_reason: Optional[str]


def circular_weighted_fusion(
    xgb_hour: float,
    state_hour: float,
    weights: FusionWeights,
    config: FusionConfig = DEFAULT_FUSION_CONFIG,
    fallback_hour: Optional[float] = None,
    fallback_reason_prefix: str = "",
) -> CircularFusionResult:
    """Combine two clock hours via weighted unit-circle vector addition.

    ``x = wxgb*cos_xgb + wstate*cos_state``, ``y = wxgb*sin_xgb +
    wstate*sin_state``; if the resulting vector's magnitude is
    (numerically) zero -- e.g. two estimates exactly 12 hours apart with
    equal weight -- this does **not** pick an arbitrary angle. It
    returns ``fallback_hour`` (the caller's documented fallback, e.g.
    the previous fused DLMO) if given, recording why, rather than
    silently producing a meaningless decoded angle.
    """

    sin_xgb, cos_xgb = clock_to_sincos(xgb_hour)
    sin_state, cos_state = clock_to_sincos(state_hour)

    x = weights.xgb * cos_xgb + weights.state * cos_state
    y = weights.xgb * sin_xgb + weights.state * sin_state
    magnitude = math.hypot(x, y)

    if magnitude <= config.zero_magnitude_epsilon:
        reason = f"{fallback_reason_prefix}zero-magnitude circular vector (opposing estimates cancelled out)"
        return CircularFusionResult(
            fused_hour=fallback_hour, vector_magnitude=magnitude, used_fallback=True, fallback_reason=reason
        )

    fused_hour = sincos_to_clock(y / magnitude, x / magnitude)
    return CircularFusionResult(fused_hour=fused_hour, vector_magnitude=magnitude, used_fallback=False, fallback_reason=None)

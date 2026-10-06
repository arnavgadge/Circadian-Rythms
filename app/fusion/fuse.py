"""The DLMO fusion layer: the single ``fuse()`` entry point.

Combines the Phase 5 XGBoost estimate and the Phase 6 state-engine
estimate into one authoritative fused DLMO, through the locked
four-layer Q26 model, in order:

    1. base weights from data quality        (app.fusion.weights.get_base_weights)
    2. disagreement adjustment                (app.fusion.weights.classify_disagreement / adjust_weights)
    3. biological continuity constraint       (app.fusion.continuity.apply_continuity_cap)
    4. confidence penalty                     (app.fusion.confidence.apply_confidence_penalty)

This module is pure computation: it never queries the database and
never imports the trained XGBoost model or the state engine's own
transition logic -- it only combines two already-computed hour values
handed to it by the caller (the future Phase 11 daily pipeline).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from app.fusion.circular_fusion import circular_weighted_fusion
from app.fusion.config import DEFAULT_FUSION_CONFIG, ConfidenceLabel, DisagreementRegime, FusionConfig
from app.fusion.confidence import (
    DataQualityInput,
    apply_confidence_penalty,
    confidence_label,
    get_base_confidence,
    should_suppress_prediction,
)
from app.fusion.continuity import ContinuityResult, apply_continuity_cap
from app.fusion.weights import FusionWeights, adjust_weights, classify_disagreement, get_base_weights
from app.synthetic.time_utils import circular_diff_hours, normalize_hour


@dataclass(frozen=True)
class FusionResult:
    """Everything the fusion layer produced, for both downstream use and diagnostics."""

    # Inputs, as received (sanitized: NaN/Inf/None all surface as None).
    xgb_dlmo: Optional[float]
    state_dlmo: Optional[float]
    previous_fused_dlmo: Optional[float]

    # Model availability (distinct from data quality -- see module docstring).
    xgb_available: bool
    state_available: bool

    # Fusion math.
    fused_before_continuity: Optional[float]
    fused_final: Optional[float]
    xgb_base_weight: float
    state_base_weight: float
    xgb_final_weight: float
    state_final_weight: float

    # Disagreement (None when fewer than two estimators are available).
    disagreement_minutes: Optional[float]
    disagreement_regime: Optional[DisagreementRegime]

    # Continuity.
    continuity_cap_minutes: float
    continuity_applied: bool
    continuity_adjustment_minutes: float

    # Confidence.
    base_confidence: float
    confidence_penalty: float
    final_confidence: float
    confidence_label: ConfidenceLabel

    # Decision surface for the caller.
    prediction_made: bool
    is_approximate: bool

    # Numerical-robustness bookkeeping.
    used_fallback: bool
    fallback_reason: Optional[str]


def _sanitize_hour(value: Optional[float]) -> Optional[float]:
    """None/NaN/Infinity all become ``None`` ("unavailable"); any other
    finite value is wrapped into ``[0, 24)``."""

    if value is None:
        return None
    if not math.isfinite(value):
        return None
    return normalize_hour(value)


def _resolve_fallback_hour(
    previous_hour: Optional[float], state_hour: Optional[float], xgb_hour: Optional[float]
) -> tuple:
    """Documented fallback order when no principled estimate is available:
    previous fused DLMO, then state, then XGBoost, then nothing."""

    if previous_hour is not None:
        return previous_hour, "previous_fused_dlmo"
    if state_hour is not None:
        return state_hour, "state_dlmo"
    if xgb_hour is not None:
        return xgb_hour, "xgb_dlmo"
    return None, "no_estimate_available"


def fuse(
    xgb_dlmo: Optional[float],
    state_dlmo: Optional[float],
    previous_fused_dlmo: Optional[float],
    data_quality: DataQualityInput,
    config: FusionConfig = DEFAULT_FUSION_CONFIG,
) -> FusionResult:
    """Fuse the two independent daily DLMO estimates. Pure and deterministic."""

    xgb_hour = _sanitize_hour(xgb_dlmo)
    state_hour = _sanitize_hour(state_dlmo)
    previous_hour = _sanitize_hour(previous_fused_dlmo)

    xgb_available = xgb_hour is not None
    state_available = state_hour is not None

    base_confidence = get_base_confidence(data_quality, config)
    base_weights = get_base_weights(data_quality.tier, config)

    used_fallback = False
    fallback_reason: Optional[str] = None

    if not xgb_available and not state_available:
        # Both estimators unavailable: no mathematically available estimate at all.
        fallback_hour, reason = _resolve_fallback_hour(previous_hour, state_hour, xgb_hour)
        return FusionResult(
            xgb_dlmo=xgb_hour, state_dlmo=state_hour, previous_fused_dlmo=previous_hour,
            xgb_available=False, state_available=False,
            fused_before_continuity=fallback_hour, fused_final=fallback_hour,
            xgb_base_weight=base_weights.xgb, state_base_weight=base_weights.state,
            xgb_final_weight=0.0, state_final_weight=0.0,
            disagreement_minutes=None, disagreement_regime=None,
            continuity_cap_minutes=config.default_continuity_cap_minutes, continuity_applied=False, continuity_adjustment_minutes=0.0,
            base_confidence=base_confidence, confidence_penalty=0.0, final_confidence=0.0,
            confidence_label=ConfidenceLabel.NO_PREDICTION,
            prediction_made=False, is_approximate=False,
            used_fallback=fallback_hour is not None, fallback_reason=reason,
        )

    if xgb_available and state_available:
        disagreement_minutes = abs(circular_diff_hours(xgb_hour, state_hour) * 60.0)
        regime = classify_disagreement(disagreement_minutes, config)
        final_weights = adjust_weights(base_weights, regime, config)
        confidence_penalty = config.confidence_penalty_by_regime[regime]
        continuity_cap = config.continuity_cap_minutes_by_regime[regime]

        fallback_hour, fallback_reason_candidate = _resolve_fallback_hour(previous_hour, state_hour, xgb_hour)
        circ_result = circular_weighted_fusion(
            xgb_hour, state_hour, final_weights, config,
            fallback_hour=fallback_hour, fallback_reason_prefix="fuse(): ",
        )
        fused_before_continuity = circ_result.fused_hour
        if circ_result.used_fallback:
            used_fallback = True
            fallback_reason = circ_result.fallback_reason
    else:
        # Exactly one estimator available: degraded single-source path.
        disagreement_minutes = None
        regime = None
        confidence_penalty = config.single_estimator_confidence_penalty
        continuity_cap = config.default_continuity_cap_minutes
        if xgb_available:
            final_weights = FusionWeights(xgb=1.0, state=0.0)
            fused_before_continuity = xgb_hour
        else:
            final_weights = FusionWeights(xgb=0.0, state=1.0)
            fused_before_continuity = state_hour

    if fused_before_continuity is None:
        # The zero-magnitude fallback chain found nothing usable either.
        confidence_after_penalty = 0.0
        return FusionResult(
            xgb_dlmo=xgb_hour, state_dlmo=state_hour, previous_fused_dlmo=previous_hour,
            xgb_available=xgb_available, state_available=state_available,
            fused_before_continuity=None, fused_final=None,
            xgb_base_weight=base_weights.xgb, state_base_weight=base_weights.state,
            xgb_final_weight=final_weights.xgb, state_final_weight=final_weights.state,
            disagreement_minutes=disagreement_minutes, disagreement_regime=regime,
            continuity_cap_minutes=continuity_cap, continuity_applied=False, continuity_adjustment_minutes=0.0,
            base_confidence=base_confidence, confidence_penalty=confidence_penalty, final_confidence=confidence_after_penalty,
            confidence_label=ConfidenceLabel.NO_PREDICTION,
            prediction_made=False, is_approximate=False,
            used_fallback=True, fallback_reason=fallback_reason or "no_estimate_available",
        )

    # Layer 3: continuity, anchored on the previous FUSED DLMO (never a raw estimator).
    if previous_hour is not None:
        continuity_result: ContinuityResult = apply_continuity_cap(fused_before_continuity, previous_hour, continuity_cap)
    else:
        continuity_result = ContinuityResult(
            final_hour=fused_before_continuity, applied=False, adjustment_minutes=0.0, raw_delta_minutes=0.0
        )
    fused_final = continuity_result.final_hour

    # Layer 4: confidence penalty.
    confidence_after_penalty = apply_confidence_penalty(base_confidence, regime, config) if regime is not None else max(
        0.0, min(100.0, base_confidence + confidence_penalty)
    )
    label = confidence_label(confidence_after_penalty, config)

    prediction_made = not should_suppress_prediction(data_quality, confidence_after_penalty, config)
    is_approximate = label == ConfidenceLabel.LOW

    return FusionResult(
        xgb_dlmo=xgb_hour, state_dlmo=state_hour, previous_fused_dlmo=previous_hour,
        xgb_available=xgb_available, state_available=state_available,
        fused_before_continuity=fused_before_continuity, fused_final=fused_final,
        xgb_base_weight=base_weights.xgb, state_base_weight=base_weights.state,
        xgb_final_weight=final_weights.xgb, state_final_weight=final_weights.state,
        disagreement_minutes=disagreement_minutes, disagreement_regime=regime,
        continuity_cap_minutes=continuity_cap, continuity_applied=continuity_result.applied,
        continuity_adjustment_minutes=continuity_result.adjustment_minutes,
        base_confidence=base_confidence, confidence_penalty=confidence_penalty, final_confidence=confidence_after_penalty,
        confidence_label=label,
        prediction_made=prediction_made, is_approximate=is_approximate,
        used_fallback=used_fallback, fallback_reason=fallback_reason,
    )

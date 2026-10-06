"""Layers 1-2 of the Q26 fusion model: base weights and disagreement-based adjustment."""

from __future__ import annotations

from dataclasses import dataclass

from app.fusion.config import DEFAULT_FUSION_CONFIG, DataQualityTier, DisagreementRegime, FusionConfig


@dataclass(frozen=True)
class FusionWeights:
    xgb: float
    state: float

    def __post_init__(self) -> None:
        total = self.xgb + self.state
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"FusionWeights must sum to 1.0, got xgb={self.xgb} + state={self.state} = {total}")


def get_base_weights(tier: DataQualityTier, config: FusionConfig = DEFAULT_FUSION_CONFIG) -> FusionWeights:
    """Layer 1: base weights from data quality (locked Q26 values)."""

    xgb, state = config.base_weights_by_tier[tier]
    return FusionWeights(xgb=xgb, state=state)


_BOUNDARY_EPSILON_MINUTES = 1e-6


def classify_disagreement(minutes: float, config: FusionConfig = DEFAULT_FUSION_CONFIG) -> DisagreementRegime:
    """Classify a (non-negative) disagreement magnitude in minutes into a regime.

    Boundaries are inclusive on the upper end of each band: exactly 20
    minutes is NORMAL, exactly 45 is MODERATE, exactly 75 is LARGE;
    anything greater than 75 is EXTREME. A tiny epsilon is applied to
    each comparison so a value that is "exactly" a boundary in intent
    but lands a few ULPs over it after upstream circular-arithmetic
    floating-point error (e.g. 23:50 to 00:10 computed as
    20.000000000000142 minutes instead of exactly 20) still classifies
    as intended, without changing the boundaries themselves.
    """

    normal_max, moderate_max, large_max = config.disagreement_thresholds_minutes
    minutes = abs(minutes)
    if minutes <= normal_max + _BOUNDARY_EPSILON_MINUTES:
        return DisagreementRegime.NORMAL
    if minutes <= moderate_max + _BOUNDARY_EPSILON_MINUTES:
        return DisagreementRegime.MODERATE
    if minutes <= large_max + _BOUNDARY_EPSILON_MINUTES:
        return DisagreementRegime.LARGE
    return DisagreementRegime.EXTREME


def adjust_weights(
    base_weights: FusionWeights,
    regime: DisagreementRegime,
    config: FusionConfig = DEFAULT_FUSION_CONFIG,
) -> FusionWeights:
    """Layer 2: reduce the XGBoost weight according to the disagreement
    regime, giving the remainder to the state weight.

    Never produces a negative weight: the reduction is clamped so XGB's
    weight cannot drop below zero, and state always receives exactly
    ``1 - xgb`` so the pair stays normalized to sum to 1.0.
    """

    reduction = config.xgb_weight_reduction_by_regime[regime]
    new_xgb = max(0.0, base_weights.xgb - reduction)
    new_state = 1.0 - new_xgb
    return FusionWeights(xgb=new_xgb, state=new_state)

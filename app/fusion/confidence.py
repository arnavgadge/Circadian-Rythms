"""Layer 4 of the Q26 fusion model: the confidence penalty, plus the
(reused, not reinvented) Q25 confidence-label thresholds and the
no-prediction suppression rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.fusion.config import DEFAULT_FUSION_CONFIG, ConfidenceLabel, DataQualityTier, DisagreementRegime, FusionConfig


@dataclass(frozen=True)
class DataQualityInput:
    """What the fusion layer needs from the upstream data-quality system.

    ``tier`` selects the Layer-1 base weights. ``window_completeness``
    and ``tier1_signals_missing`` feed the no-prediction rule.
    ``base_confidence``, if given, overrides Phase 7's minimal
    tier-based default (see ``app.fusion.config`` module docstring) --
    pass it once an upstream system actually computes one.
    """

    tier: DataQualityTier
    window_completeness: float
    tier1_signals_missing: bool = False
    base_confidence: float | None = None


def get_base_confidence(data_quality: DataQualityInput, config: FusionConfig = DEFAULT_FUSION_CONFIG) -> float:
    """The confidence score the penalty layer operates on.

    Uses ``data_quality.base_confidence`` if the caller supplied one;
    otherwise falls back to Phase 7's minimal tier-based default.
    """

    if data_quality.base_confidence is not None:
        return data_quality.base_confidence
    return config.base_confidence_by_tier[data_quality.tier]


def apply_confidence_penalty(
    base_confidence: float,
    regime: DisagreementRegime,
    config: FusionConfig = DEFAULT_FUSION_CONFIG,
) -> float:
    """Layer 4: apply the disagreement-regime confidence penalty, clamped to [0, 100]."""

    penalty = config.confidence_penalty_by_regime[regime]
    return max(0.0, min(100.0, base_confidence + penalty))


def confidence_label(score: float, config: FusionConfig = DEFAULT_FUSION_CONFIG) -> ConfidenceLabel:
    """The Q25 confidence label thresholds, reused unchanged."""

    high_min, moderate_min, low_min = config.confidence_label_thresholds
    if score >= high_min:
        return ConfidenceLabel.HIGH
    if score >= moderate_min:
        return ConfidenceLabel.MODERATE
    if score >= low_min:
        return ConfidenceLabel.LOW
    return ConfidenceLabel.NO_PREDICTION


def should_suppress_prediction(
    data_quality: DataQualityInput, confidence: float, config: FusionConfig = DEFAULT_FUSION_CONFIG
) -> bool:
    """Whether the upstream data-quality rules require suppressing a
    normal user-facing prediction, regardless of whether a fused value
    was mathematically computable.

    True if ALL critical Tier-1 inputs are missing, OR window
    completeness is below 50%, OR confidence is below 40.
    """

    return (
        data_quality.tier1_signals_missing
        or data_quality.window_completeness < config.no_prediction_completeness_threshold
        or confidence < config.no_prediction_confidence_threshold
    )

"""The completeness -> ``DataQualityTier`` mapping the fusion layer
needs but does not itself define (see ``app.fusion.config`` module
docstring: Phase 7 accepts a pre-computed tier/confidence and leaves
deciding one from a completeness fraction to the caller). This is the
single place the live pipeline makes that decision, reusing the exact
thresholds ``app.scripts.run_fusion_diagnostics`` already established
for the same purpose.
"""

from __future__ import annotations

from app.fusion.confidence import DataQualityInput
from app.fusion.config import DataQualityTier
from app.pipeline.config import DEFAULT_PIPELINE_CONFIG, PipelineConfig


def completeness_to_tier(completeness: float, config: PipelineConfig = DEFAULT_PIPELINE_CONFIG) -> DataQualityTier:
    if completeness >= config.high_completeness_threshold:
        return DataQualityTier.HIGH
    if completeness >= config.moderate_completeness_threshold:
        return DataQualityTier.MODERATE
    if completeness >= config.low_completeness_threshold:
        return DataQualityTier.LOW
    return DataQualityTier.VERY_LOW


def build_data_quality_input(feature_vector, config: PipelineConfig = DEFAULT_PIPELINE_CONFIG) -> DataQualityInput:
    tier1_missing = feature_vector.tier_missing_counts.get("tier_1", 0) >= config.tier1_missing_count_threshold
    return DataQualityInput(
        tier=completeness_to_tier(feature_vector.completeness, config),
        window_completeness=feature_vector.completeness,
        tier1_signals_missing=tier1_missing,
    )


def insufficient_history_data_quality() -> DataQualityInput:
    """The degenerate data-quality input used during the Q23 onboarding
    window (fewer than 6 consecutive prior days), when the Phase 4
    feature engine cannot run at all -- fusion is still called (with
    ``xgb_dlmo=None``) so its own documented fallback chain
    (``previous_fused -> state -> xgb -> None``) and confidence
    penalties apply consistently rather than the pipeline inventing a
    parallel "no data" special case."""

    return DataQualityInput(tier=DataQualityTier.VERY_LOW, window_completeness=0.0, tier1_signals_missing=True)

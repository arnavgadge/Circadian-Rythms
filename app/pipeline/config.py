"""Configuration for the Phase 11 daily inference pipeline.

The pipeline orchestrates Phases 4-10; it does not own any of their
scientific parameters (those stay in each phase's own versioned config
module). What lives here is purely **orchestration** configuration:
which model artifact version to load, the Q23 onboarding-schedule
threshold, and the data-quality-tier mapping this pipeline itself is
responsible for deciding (no earlier phase computes a
completeness -> ``DataQualityTier`` mapping; Phase 7's own diagnostic
script uses the same thresholds locally -- reused here as the single
place the live pipeline makes that decision).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineConfig:
    pipeline_config_version: str = "1.0.0"

    # --- Model artifact selection ---
    # Which trained Phase 5 XGBoost artifact version to load. Explicit,
    # never "whichever file happens to exist" -- see
    # app.pipeline.xgboost_step.
    xgboost_model_version: int = 1

    # --- Q23 onboarding schedule ---
    # Number of consecutive, complete prior days required before the
    # six-day feature window (and therefore XGBoost) can run at all.
    min_consecutive_history_days: int = 6

    # --- Data-quality tier thresholds (completeness -> DataQualityTier) ---
    # Reuses the exact thresholds app.scripts.run_fusion_diagnostics
    # already uses for the same purpose -- not a new, competing
    # definition, just the first time it is applied in a live pipeline
    # rather than only in a diagnostic script.
    high_completeness_threshold: float = 0.95
    moderate_completeness_threshold: float = 0.80
    low_completeness_threshold: float = 0.50
    # Number of missing tier-1 (highest-priority) features at/above
    # which tier-1 signals are considered missing for the fusion
    # layer's no-prediction rule -- mirrors the same diagnostic-script
    # convention.
    tier1_missing_count_threshold: int = 3

    # --- Participant-trait fallbacks (documented production defaults) ---
    # ``baseline_sleep_onset_hour`` and the behavioral sensitivities are
    # Phase 3 synthetic-generation concepts, not columns on
    # ``participant_profiles`` (see app.state.db_adapter). For a
    # synthetic participant they are read back out of
    # ``synthetic_personality_profile``; for any participant lacking
    # that JSON blob, these are the documented fallbacks:
    default_sensitivity: float = 1.0
    # Empirical proxy: the mean of the six-day window's actual sleep
    # onset -- there is no stored "habitual, behavior-free" sleep onset
    # for a non-synthetic participant, so recent observed behavior is
    # the closest available stand-in, clearly documented as an
    # approximation rather than the true synthetic-generation trait.
    baseline_sleep_onset_fallback_offset_hours: float = 2.0  # used only if the window itself is unusable


DEFAULT_PIPELINE_CONFIG = PipelineConfig()

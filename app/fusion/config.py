"""Configuration for the CircadianIQ DLMO fusion layer.

Every numeric parameter used by the four-layer fusion model (base
weights, disagreement thresholds, weight reductions, continuity caps,
confidence penalties, confidence-label thresholds) lives here. These
are the project's **locked Q26 design parameters** -- engineering/
project decisions, not experimentally validated biological constants.
Nothing in this module is claimed to be clinically validated.

Two mappings in this file are **not** part of the locked Q26 spec and
are Phase 7's own minimal, clearly-labeled defaults, introduced only
because no earlier phase built the piece they fill in:

- ``base_confidence_by_tier``: the brief says the confidence *penalty*
  "applies to the confidence score produced by the data-quality
  system", but no earlier phase actually computes a numeric 0-100 base
  confidence from a data-quality tier. This mapping is that missing
  starting point -- not a competing confidence model, just a plain,
  documented default a later phase is free to replace outright without
  touching the fusion algorithm itself (:func:`app.fusion.fuse.fuse`
  accepts a pre-computed ``base_confidence`` directly and only falls
  back to this mapping when one isn't supplied).
- ``single_estimator_confidence_penalty``: the brief says confidence
  "must be reduced appropriately" when only one estimator is available,
  without specifying by how much; this is Phase 7's chosen value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DataQualityTier(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    VERY_LOW = "very_low"


class DisagreementRegime(str, Enum):
    NORMAL = "normal"
    MODERATE = "moderate"
    LARGE = "large"
    EXTREME = "extreme"


class ConfidenceLabel(str, Enum):
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    NO_PREDICTION = "no_prediction"


@dataclass(frozen=True)
class FusionConfig:
    """All Q26 fusion parameters, versioned."""

    fusion_config_version: str = "1.0.0"

    # --- Layer 1: base weights by data quality (locked Q26 values) ---
    base_weights_by_tier: dict = field(
        default_factory=lambda: {
            DataQualityTier.HIGH: (0.65, 0.35),
            DataQualityTier.MODERATE: (0.55, 0.45),
            DataQualityTier.LOW: (0.40, 0.60),
            DataQualityTier.VERY_LOW: (0.20, 0.80),
        }
    )

    # --- Layer 2: disagreement regime thresholds (minutes, inclusive upper bound) ---
    disagreement_thresholds_minutes: tuple = (20.0, 45.0, 75.0)  # normal|moderate|large boundaries; > last = extreme

    # XGBoost weight reduction applied per disagreement regime (locked Q26 values).
    xgb_weight_reduction_by_regime: dict = field(
        default_factory=lambda: {
            DisagreementRegime.NORMAL: 0.0,
            DisagreementRegime.MODERATE: 0.10,
            DisagreementRegime.LARGE: 0.20,
            DisagreementRegime.EXTREME: 0.30,
        }
    )

    # --- Layer 3: continuity caps by disagreement regime, minutes/day (locked Q26 values) ---
    continuity_cap_minutes_by_regime: dict = field(
        default_factory=lambda: {
            DisagreementRegime.NORMAL: 60.0,
            DisagreementRegime.MODERATE: 45.0,
            DisagreementRegime.LARGE: 30.0,
            DisagreementRegime.EXTREME: 20.0,
        }
    )
    # Used only when disagreement is not applicable (a single estimator
    # is available, or there is no previous fused value to compare
    # against) -- a Phase 7 design choice, not a Q26-specified value.
    default_continuity_cap_minutes: float = 60.0

    # --- Layer 4: confidence penalties by disagreement regime (locked Q26 values) ---
    confidence_penalty_by_regime: dict = field(
        default_factory=lambda: {
            DisagreementRegime.NORMAL: 0.0,
            DisagreementRegime.MODERATE: -8.0,
            DisagreementRegime.LARGE: -18.0,
            DisagreementRegime.EXTREME: -30.0,
        }
    )

    # --- Confidence labels (locked Q25 thresholds, reused unchanged) ---
    confidence_label_thresholds: tuple = (80.0, 60.0, 40.0)  # high|moderate|low boundaries; < last = no_prediction

    # --- No-prediction conditions ---
    no_prediction_completeness_threshold: float = 0.5  # < 50% window completeness suppresses prediction
    no_prediction_confidence_threshold: float = 40.0  # confidence < 40 suppresses prediction

    # --- Phase-7-introduced defaults (see module docstring) ---
    base_confidence_by_tier: dict = field(
        default_factory=lambda: {
            DataQualityTier.HIGH: 90.0,
            DataQualityTier.MODERATE: 70.0,
            DataQualityTier.LOW: 50.0,
            DataQualityTier.VERY_LOW: 20.0,
        }
    )
    single_estimator_confidence_penalty: float = -15.0

    # --- Numerical robustness ---
    zero_magnitude_epsilon: float = 1e-9


DEFAULT_FUSION_CONFIG = FusionConfig()

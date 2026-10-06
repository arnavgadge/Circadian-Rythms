"""Configuration for the Phase 14 safety + confidence layer.

Confidence *thresholds* are not redeclared here -- they are consumed
directly from ``app.fusion.config.DEFAULT_FUSION_CONFIG.confidence_label_thresholds``
(already `(80, 60, 40)`, the exact locked values this phase requires),
so this module cannot silently drift out of sync with the fusion
layer's own confidence decision (see module docstring in
``app.safety.confidence_gate``).

Everything below is a **project screening parameter**, explicitly not
claimed as a clinically validated diagnostic threshold -- see
``docs/safety_and_confidence.md`` "Limitations".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SafetyConfig:
    safety_config_version: str = "1.0.0"

    # --- Rolling pattern-detection horizon ---
    rolling_horizon_days: int = 14
    # A flag is never raised from fewer than this many *available*
    # (prediction_available=True) observations within the horizon --
    # days with no prediction are excluded from evidence, never
    # counted as supporting a trend.
    min_observations_for_flag: int = 10

    # --- Flag 1: persistent late phase ---
    late_phase_threshold_hour: float = 2.0  # ~2:00 AM

    # --- Flag 4: persistent early phase ---
    early_phase_threshold_hour: float = 19.5  # ~7:30 PM

    # --- Flag 3: continuous DLMO drift ---
    drift_threshold_minutes_per_day: float = 20.0

    # --- Flag 2: low alignment despite compliance ---
    low_alignment_threshold: float = 45.0
    high_compliance_threshold: float = 0.70

    # --- Flag resolution (hysteresis) ---
    # A flag is only resolved once the pattern fails to re-trigger over
    # this many of the most recent *available* observations -- a single
    # normal day never resolves a persistent flag.
    resolution_min_normal_observations: int = 7

    # --- Severity assignment (locked: only MODERATE/HIGH exist) ---
    high_severity_flag_types: tuple = ("continuous_dlmo_drift",)
    # Every other flag type (persistent_late_phase, persistent_early_phase,
    # low_alignment_despite_compliance) is MODERATE.

    # --- Safe recommendation catalogue ---
    approved_intervention_types: tuple = ("screen", "light", "meal", "exercise", "caffeine", "sleep")


DEFAULT_SAFETY_CONFIG = SafetyConfig()

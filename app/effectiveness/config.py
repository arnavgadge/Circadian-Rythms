"""Configuration for the Phase 12 intervention-feedback/effectiveness
system.

Every threshold used anywhere in ``app.effectiveness`` lives here --
**all project design choices**, not clinically validated constants.
The three measurement phases carry increasingly strong (but still
non-causal, for phases 1-2) interpretation labels; see
``docs/intervention_effectiveness.md`` "Scientific limitations".
"""

from __future__ import annotations

from dataclasses import dataclass, field

OBSERVATIONAL = "observational"
MATCHED_OBSERVATIONAL = "matched_observational"
REGRESSION_CONTROLLED_ESTIMATE = "regression_controlled_estimate"

PHASE_INTERPRETATION = {1: OBSERVATIONAL, 2: MATCHED_OBSERVATIONAL, 3: REGRESSION_CONTROLLED_ESTIMATE}


@dataclass(frozen=True)
class EffectivenessConfig:
    effectiveness_config_version: str = "1.0.0"

    # --- Compliance ---
    compliance_binary_threshold: float = 0.65
    # Per-intervention-type decay constant (minutes, or the value's own
    # native unit for duration-based signals) controlling how quickly
    # compliance degrades once behavior falls on the wrong side of the
    # target -- see app.effectiveness.compliance. A project default,
    # not derived from any adherence-science citation.
    compliance_decay_by_intervention_type: dict = field(
        default_factory=lambda: {
            "screen": 30.0,
            "light": 20.0,
            "meal": 45.0,
            "exercise": 45.0,
            "caffeine": 45.0,
            "sleep": 30.0,  # social-jetlag-style "consistent schedule" interventions
        }
    )

    # --- Phase 1: before/after windows ---
    baseline_window_days: int = 7
    intervention_window_days: int = 7
    # A day counts as "observed" for window purposes only when its
    # fused DLMO/alignment score exists; missing days are excluded
    # from period means, never treated as zero/failure.
    min_window_completeness: float = 0.5  # >= 50% of the window days must be observed

    # --- Confound detection ---
    # A non-target signal is flagged as a possible confound when its
    # baseline-vs-intervention change exceeds this magnitude. Units
    # match each signal's own native unit (minutes for clock-time
    # signals, minutes for durations/jetlag).
    confound_thresholds: dict = field(
        default_factory=lambda: {
            "morning_light": 15.0,   # minutes duration change
            "evening_screen": 20.0,  # minutes cutoff-time change
            "meal_timing": 20.0,     # minutes clock-time change
            "exercise": 30.0,        # minutes clock-time change
            "social_jetlag": 20.0,   # minutes change
        }
    )

    # --- Phase 2: matched-period comparison ---
    min_history_days_for_phase2: int = 28  # "approximately four weeks"
    min_matched_period_days: int = 7
    # Standardized (z-scored) mean distance across matched (non-target)
    # variables; a candidate period is accepted only below this.
    max_match_distance: float = 1.0
    min_match_data_completeness: float = 0.6

    # --- Phase 3: regression ---
    min_regression_observations: int = 21  # "21+: stronger personal evidence"
    confidence_level: float = 0.95

    # --- Personal-history evidence tiers (informational, not a gate by itself) ---
    early_evidence_min_observations: int = 7
    strong_evidence_min_observations: int = 21


DEFAULT_EFFECTIVENESS_CONFIG = EffectivenessConfig()

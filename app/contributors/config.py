"""Configuration for the CircadianIQ contributor ranking engine.

Every weight, threshold, and normalization parameter used anywhere in
``app.contributors`` lives here. **All of these are project design
choices, not scientifically validated universal weights** -- see
``docs/contributor_ranking.md`` for the full discussion.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContributorConfig:
    contributor_config_version: str = "1.0.0"

    # --- Composite score (locked architecture) ---
    phase_effect_weight: float = 0.60
    alignment_deficit_weight: float = 0.40

    # --- Significance threshold ---
    # A ranked contributor's score below this is reported as "neutral"
    # rather than presented as a meaningful cause -- prevents weak noise
    # from looking like a major contributor merely by ranking #1.
    significance_threshold: float = 20.0

    # --- Direction classification ---
    # If |phase deviation| is below this, the participant is considered
    # "already well aligned" and no signal is classified hurting/opportunity
    # -- everything reports neutral regardless of its own effect sign.
    phase_deviation_neutral_zone_minutes: float = 10.0
    # A corrective-direction effect smaller than this (in minutes) is
    # "weak" -> opportunity_missed rather than neutral.
    weak_corrective_effect_minutes_threshold: float = 15.0

    # --- Anomaly detection ---
    min_history_days_for_anomaly: int = 3  # fewer usable window days -> anomaly unavailable
    anomaly_modified_z_threshold: float = 3.5  # standard robust-outlier threshold (Iglewicz & Hoaglin)
    mad_epsilon: float = 1e-6  # MAD below this treated as "zero variance" -> fallback path
    # Fallback absolute-deviation thresholds used only when the personal
    # window has (near-)zero variance, per signal, in the signal's own
    # native units (minutes for clock-time/duration signals, mg for
    # caffeine -- unused here, minutes for jetlag).
    fallback_absolute_threshold_minutes: float = 30.0

    # --- Effect normalization ---
    # If every candidate signal's absolute phase effect is (numerically)
    # zero, all normalized effects are 0 rather than a divide-by-zero.
    zero_effect_epsilon: float = 1e-9


DEFAULT_CONTRIBUTOR_CONFIG = ContributorConfig()

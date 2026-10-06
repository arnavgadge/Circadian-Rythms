"""Configuration for the CircadianIQ recommendation engine.

Every threshold, weight, and default assumption used anywhere in
``app.recommendations`` lives here. **All numeric values are project
design choices**, not independently validated clinical or scientific
constants -- see ``docs/recommendation_engine.md`` for the full
discussion, including which fields additionally carry a
"synthetic assumption" label because no verified literature citation
backs them.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SeverityWeights:
    impact_weight: float
    feasibility_weight: float


@dataclass(frozen=True)
class RecommendationConfig:
    recommendation_config_version: str = "1.0.0"

    # --- Misalignment severity bands (project design choice; see
    # docs/recommendation_engine.md "Severity model") ---
    severity_good_threshold: float = 80.0
    severity_mild_threshold: float = 60.0
    severity_moderate_threshold: float = 40.0
    # alignment < severity_moderate_threshold -> SEVERE

    # --- Severity -> impact/feasibility weighting (locked strategy) ---
    severe_weights: SeverityWeights = field(default_factory=lambda: SeverityWeights(0.55, 0.45))
    moderate_weights: SeverityWeights = field(default_factory=lambda: SeverityWeights(0.45, 0.55))
    mild_weights: SeverityWeights = field(default_factory=lambda: SeverityWeights(0.35, 0.65))
    # GOOD/highly-aligned participants: strongly favor low-burden
    # maintenance nudges over aggressive correction.
    good_weights: SeverityWeights = field(default_factory=lambda: SeverityWeights(0.20, 0.80))

    # --- Contributor relevance ---
    # Relevance multiplier by the contributor's rank among the
    # participant's top-3 ranked signals (Phase 9). A candidate whose
    # mapped signal is not among the top 3 (or not significant) gets 0.
    relevance_by_rank: tuple = (1.0, 0.6, 0.3)
    # Bonus added (capped at 1.0) when one intervention's declared
    # ``contributor_signals`` covers more than one significant
    # top-ranked contributor -- prefers consolidating actions over
    # recommending near-duplicates.
    multi_signal_relevance_bonus: float = 0.15
    # A candidate below this relevance is dropped from primary/
    # supporting consideration entirely (unless no candidate clears it
    # at all, in which case the engine falls back to the best-scoring
    # candidate overall rather than returning nothing).
    min_relevance_threshold: float = 0.25

    # --- Graduated target ---
    # "Ask for roughly half the theoretically ideal change" -- a
    # locked, deliberately conservative adherence strategy, not a
    # clinical titration schedule.
    graduated_target_fraction: float = 0.50
    # Conservative default bound (minutes) used only when a catalogue
    # entry does not declare its own max-shift-per-recommendation --
    # explicitly a project default assumption, not a safety limit
    # derived from any clinical source.
    default_max_shift_minutes: float = 120.0

    # --- Feasibility ---
    default_baseline_feasibility: float = 0.6
    # How much a recent compliance rate (0-1) pulls feasibility away
    # from the catalogue baseline, e.g. rate=1.0 -> +compliance_weight,
    # rate=0.0 -> -compliance_weight.
    compliance_feasibility_weight: float = 0.30
    # Feasibility penalty (0-1 scale) applied in proportion to how much
    # of the intervention's own max-shift bound the graduated target
    # actually uses (a target using 100% of the allowed shift is
    # considered maximally difficult).
    target_difficulty_feasibility_weight: float = 0.25
    # Flat feasibility penalty applied when the same intervention was
    # logged with compliance_binary=False within the lookback window.
    recent_failure_feasibility_penalty: float = 0.20
    recent_history_lookback_days: int = 14

    # --- Cooldown / repetition ---
    # Minimum days a primary intervention should remain primary before
    # being switched, absent a clearly better-scoring alternative --
    # avoids flooding the participant with a constantly changing
    # target. Not a medical treatment schedule.
    primary_cooldown_days: int = 5
    # Score bonus applied to the currently-active primary intervention
    # while still within its cooldown window, so a close second choice
    # does not needlessly displace it.
    continuation_bonus: float = 0.08
    # A recent primary is only continued if its own score is at least
    # this fraction of the best candidate's score (an outright bad
    # continuing choice is still replaced).
    continuation_minimum_relative_score: float = 0.70

    # --- Selection shape ---
    max_supporting_recommendations: int = 2

    # --- Missing-data confidence reduction ---
    # Multiplies contributor_relevance when the underlying Phase 9
    # contributor's data_quality is "imputed" (never "unavailable" --
    # those candidates are excluded outright, see engine.py).
    imputed_data_relevance_multiplier: float = 0.6

    # --- Personalization compatibility ---
    # When PERSONAL_EFFECT is active, whether to average the personal
    # effect with the literature value (source="blended") instead of
    # fully overriding it (source="personal").
    blend_personal_and_literature: bool = False


DEFAULT_RECOMMENDATION_CONFIG = RecommendationConfig()

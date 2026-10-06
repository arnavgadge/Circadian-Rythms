"""Configuration for the CircadianIQ alignment engine.

Every weight, threshold, and scoring-curve parameter used anywhere in
``app.alignment`` lives here. **Every number in this file is a project
design choice, not a validated scientific constant** -- see
``docs/alignment_engine.md`` "Design assumptions vs. scientific
claims" for the full discussion. A perfect score means "aligned with
*your own* estimated phase and *your own* recent behavior", never
"matches a universal healthy schedule".

The tier boundaries the behavioral components classify against (light/
screen/meal minute and hour thresholds) are **not** redefined here:
they are imported directly from ``app.synthetic.config`` via
``app.state.behavioral_effect``'s tier classifiers, so alignment can
never silently disagree with the DLMO simulation/effect model about
what counts as, say, "heavy" evening screen use. Only the *scores*
assigned to each tier are new, Phase-8-specific design choices.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AlignmentConfig:
    alignment_config_version: str = "1.0.0"

    # --- Top-level 60/40 architecture (locked, do not change) ---
    phase_alignment_weight: float = 0.60
    behavioral_alignment_weight: float = 0.40

    # --- Behavioral component weights (locked, do not change) ---
    sleep_consistency_weight: float = 0.25
    morning_light_weight: float = 0.25
    evening_screen_weight: float = 0.20
    meal_timing_weight: float = 0.15
    social_jetlag_weight: float = 0.15

    # --- Ideal sleep timing derivation ---
    # "Ideal sleep onset = estimated DLMO + 2 hours." A project modeling
    # assumption, not a universally validated physiological constant.
    phase_to_sleep_offset_hours: float = 2.0

    # --- Phase score curve ---
    # score = 100 * exp(-|deviation_minutes| / phase_score_decay_minutes)
    # A smooth, monotonically decreasing, bounded (0, 100] curve -- the
    # specific decay constant is a Phase 8 design choice, calibrated only
    # so that small deviations score high and multi-hour deviations score
    # low (see docs/alignment_engine.md for the worked calibration table).
    phase_score_decay_minutes: float = 90.0

    # --- Sleep consistency score curve ---
    # Same exponential-decay shape, applied to the circular standard
    # deviation (in minutes) of the window's sleep-onset times -- i.e.
    # this rewards *regularity*, not any particular clock time, so a
    # consistently-early and a consistently-late sleeper can both score
    # near 100.
    sleep_consistency_decay_minutes: float = 60.0

    # --- Social jetlag score curve ---
    # score = 100 * exp(-jetlag_hours / social_jetlag_decay_hours)
    # Bounded and monotonically decreasing in jetlag; not a linear
    # `100 - k*jetlag` deduction.
    social_jetlag_decay_hours: float = 1.5

    # --- Morning light: tier -> score (Phase 8 design choice) ---
    # Tiers themselves (none/short/moderate/high) come from
    # app.synthetic.config.SyntheticAssumptions, reused unchanged.
    morning_light_tier_scores: dict = field(
        default_factory=lambda: {"none": 25.0, "short": 55.0, "moderate": 85.0, "high": 100.0}
    )

    # --- Evening screen: tier -> score (Phase 8 design choice) ---
    # Lower screen exposure scores higher; tiers reused from Phase 3/6.
    evening_screen_tier_scores: dict = field(
        default_factory=lambda: {
            "none": 100.0, "low": 85.0, "moderate": 60.0, "high": 35.0, "very_high": 10.0,
        }
    )

    # --- Meal timing: tier -> score (Phase 8 design choice) ---
    # Earlier last-meal timing scores higher; tiers reused from Phase 3/6.
    meal_timing_tier_scores: dict = field(
        default_factory=lambda: {
            "before_8pm": 100.0, "8_9pm": 80.0, "9_10pm": 55.0, "10_11pm": 30.0, "after_11pm": 10.0,
        }
    )

    # --- Missing-data fallback ---
    # Used only when a component has literally no usable data anywhere
    # in the window (not merely a single missing day) -- a neutral,
    # documented placeholder, not a claim the behavior was observed.
    neutral_fallback_score: float = 50.0

    def validate(self) -> None:
        """Raise loudly if the locked weight sums are violated."""

        top_level_sum = self.phase_alignment_weight + self.behavioral_alignment_weight
        if abs(top_level_sum - 1.0) > 1e-9:
            raise ValueError(
                f"phase_alignment_weight + behavioral_alignment_weight must equal 1.0, got {top_level_sum}"
            )

        behavioral_sum = (
            self.sleep_consistency_weight
            + self.morning_light_weight
            + self.evening_screen_weight
            + self.meal_timing_weight
            + self.social_jetlag_weight
        )
        if abs(behavioral_sum - 1.0) > 1e-9:
            raise ValueError(f"Behavioral component weights must sum to 1.0, got {behavioral_sum}")


DEFAULT_ALIGNMENT_CONFIG = AlignmentConfig()
DEFAULT_ALIGNMENT_CONFIG.validate()

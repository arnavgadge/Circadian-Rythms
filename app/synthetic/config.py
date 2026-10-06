"""Central configuration for the CircadianIQ synthetic data generator.

Every numeric constant used anywhere in ``app.synthetic`` lives in this
file, split into three explicitly labeled categories (see
``docs/synthetic_data_generation.md`` section 11 for the full
discussion):

1. :class:`SourceBackedAssumptions` -- numbers taken from
   ``CircadianIQ_Project_Document.docx`` section 5, which itself cites
   published circadian-biology literature. The docstring on each field
   repeats the citation given in that document. These are the values
   the generator treats as the closest thing it has to "real" biology.
2. :class:`SyntheticAssumptions` -- numbers this generator needed
   (curve shapes, interaction multipliers, adaptation rates, clipping
   bounds, personality parameters, sensitivity distributions) that are
   **not** backed by any source in the project's documents. They are
   modeling choices made to produce plausible, internally consistent
   synthetic behavior -- not literature-derived coefficients. No
   citation is attached to any of these because none exists; inventing
   one would violate the project's scientific-honesty rule.
3. Random variability is not a fixed value at all -- it is implemented
   as explicit noise terms drawn from the distributions declared here
   (see :mod:`app.synthetic.rng`), so it is visible in the code as
   "this is a draw from a distribution", never as a silent fudge
   factor.

Nothing here is a clinical or diagnostic threshold. All of it exists
only to produce a synthetic training/validation dataset.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceBackedAssumptions:
    """Numbers taken from the project's own literature review.

    Source document: ``CircadianIQ_Project_Document.docx``, section 5
    ("Biological Numbers Extracted from Research Papers"). That
    document in turn cites the papers named in each field's docstring.
    This code has not independently verified those papers; it treats
    the project document as the source of record, per the instruction
    to reference project documentation accurately rather than
    re-deriving or fabricating citations.
    """

    # --- 5.5 Social Jetlag / chronotype population split ---
    # Source: PMC6595939; Wittmann et al., Chronobiology International 2006.
    chronotype_population_proportions: dict = field(
        default_factory=lambda: {"early": 0.27, "intermediate": 0.59, "late": 0.14}
    )

    # --- 5.1 DLMO Distribution by chronotype (clock hour, mean +/- SD) ---
    # Source: Hunger et al., "Behavioural Parameters of Circadian Rhythm"
    # (PMC10743549).
    dlmo_mean_hour_by_chronotype: dict = field(
        default_factory=lambda: {
            "early": 20 + 24 / 60,
            "intermediate": 21 + 31 / 60,
            "late": 22 + 56 / 60,
        }
    )
    dlmo_sd_hours_by_chronotype: dict = field(
        default_factory=lambda: {"early": 42 / 60, "intermediate": 12 / 60, "late": 54 / 60}
    )

    # --- 5.2 Sleep-DLMO relationship ---
    # Source: Frontiers in Neurology (2010); Oxford "Sleep" journal (zsab126).
    # DLMO ~ sleep_onset - 2h, +/- 1h noise, r = 0.89 in the cited literature.
    # Used once per participant, at generation time, to anchor each
    # participant's stable baseline sleep-onset trait to their intrinsic
    # DLMO -- never re-applied against the evolving current_DLMO, which
    # would create the behavior<->biology feedback loop this phase
    # explicitly avoids (see docs, "Temporal ordering / leakage").
    sleep_onset_after_dlmo_hours: float = 2.0
    sleep_onset_dlmo_noise_sd_hours: float = 1.0

    # --- 5.3 Morning light -> phase advance ---
    # Source: PMC10594521; PubMed 25620199.
    # Anchor points used to calibrate the saturating response curve in
    # app.synthetic.dlmo_state; the curve shape between anchors is a
    # synthetic interpolation (see SyntheticAssumptions).
    morning_light_no_light_delay_minutes_range: tuple = (10.0, 20.0)
    morning_light_high_advance_minutes_range: tuple = (15.0, 45.0)

    # --- 5.4 Evening screen -> phase delay ---
    # Source: PMC12668929; PMC10594521.
    evening_screen_moderate_delay_minutes_range: tuple = (10.0, 30.0)
    evening_screen_heavy_delay_minutes_range: tuple = (20.0, 60.0)

    # --- 5.5 Social jetlag distribution ---
    # Source: PMC6595939; Wittmann et al., Chronobiology International 2006.
    social_jetlag_mean_hours: float = 1.0
    social_jetlag_sd_hours: float = 0.75
    social_jetlag_range_hours: tuple = (0.0, 3.0)

    # --- 5.6 Meal timing -> phase delay ---
    # Source: PMC6471585.
    late_meal_after_9pm_delay_minutes_range: tuple = (15.0, 30.0)

    # --- MEQ instrument range ---
    # Horne & Ostberg (1976), Morningness-Eveningness Questionnaire (MEQ):
    # the standard 19-item MEQ instrument scores range from 16 to 86.
    # This is a property of the published instrument itself, not a
    # project-specific finding.
    meq_score_min: int = 16
    meq_score_max: int = 86


@dataclass(frozen=True)
class SyntheticAssumptions:
    """Modeling choices with no literature backing found in the project's
    own sources. Every field here is a synthetic design decision, kept
    in one place so it can be tuned without hunting through the codebase.
    """

    # --- Behavioral personality population proportions ---
    # Synthetic design choice, not a population survey result.
    personality_proportions: dict = field(
        default_factory=lambda: {
            "consistent_early_bird": 0.08,
            "consistent_night_owl": 0.10,
            "social_jetlag_student": 0.25,
            "chaotic_sleeper": 0.12,
            "healthy_stable_routine": 0.15,
            "screen_heavy_user": 0.18,
            "late_eater": 0.12,
        }
    )

    # --- Participant sensitivity multipliers (stable, drawn once) ---
    light_sensitivity_mean: float = 1.0
    light_sensitivity_sd: float = 0.20
    screen_sensitivity_mean: float = 1.0
    screen_sensitivity_sd: float = 0.15
    meal_sensitivity_mean: float = 1.0
    meal_sensitivity_sd: float = 0.18
    sensitivity_clip_range: tuple = (0.3, 2.0)

    # --- Exercise / caffeine effects (no project source found) ---
    # Directionality follows general chronobiology plausibility (evening
    # exercise / late caffeine associated with mild phase delay; morning
    # exercise with a mild advance) but magnitudes are deliberately kept
    # small and are illustrative only -- there is no cited source for
    # these two signals anywhere in the project's documents.
    exercise_morning_advance_minutes_max: float = 8.0
    exercise_evening_delay_minutes_max: float = 8.0
    exercise_morning_cutoff_hour: float = 10.0
    exercise_evening_cutoff_hour: float = 19.0
    caffeine_late_delay_minutes_max: float = 10.0
    caffeine_late_cutoff_hour: float = 14.0

    # --- Saturating-curve shape parameters ---
    # These control HOW the response curves interpolate between the
    # source-backed anchor points above; the anchor values are cited,
    # the curve shape (exponential saturation) and time-constants below
    # are not.
    morning_light_saturation_tau_minutes: float = 22.0
    evening_screen_saturation_tau_minutes: float = 120.0
    meal_delay_saturation_tau_hours: float = 1.0

    # --- Interaction effects (explicitly synthetic; see project brief) ---
    interaction_no_light_screen_amplifier: float = 1.25
    interaction_moderate_light_screen_reduction: float = 0.75
    interaction_high_light_screen_reduction: float = 0.5
    interaction_late_sleeper_late_meal_amplifier: float = 1.3
    # A participant's stable baseline sleep onset counts as "late habitual"
    # once it falls more than `late_habitual_sleeper_margin_hours` past
    # `late_habitual_sleeper_reference_hour`, measured along the forward
    # (later) circular direction -- e.g. with the defaults below, anything
    # from 23:30 through the early morning counts as late.
    late_habitual_sleeper_reference_hour: float = 22.0
    late_habitual_sleeper_margin_hours: float = 1.5
    very_late_meal_hour_threshold: float = 23.0

    # --- Daily behavioral shift bound ---
    # A simulation-stability constraint, not a physiological maximum.
    daily_shift_clip_minutes: tuple = (-90.0, 60.0)

    # --- Three-layer DLMO state update ---
    adapted_daily_pull_to_behavior_fraction: float = 0.01  # ~1%/day
    adapted_daily_pull_to_intrinsic_fraction: float = 0.005  # ~0.5%/day
    adapted_bound_hours_from_intrinsic: float = 2.0
    current_daily_pull_to_adapted_fraction: float = 0.5
    current_bound_hours_from_intrinsic: float = 3.0
    daily_state_noise_sd_minutes: float = 5.0

    # --- Behavior generation: day-level and disruption noise ---
    day_level_noise_sd_minutes: float = 12.0
    disruption_probability: float = 0.05
    disruption_magnitude_hours_range: tuple = (1.0, 3.0)

    # --- Signal tiers used for classification / diagnostics ---
    morning_light_tier_minutes: tuple = (0.0, 10.0, 30.0)  # none|short|moderate|high boundaries
    morning_light_tier_labels: tuple = ("none", "short", "moderate", "high")
    evening_screen_tier_hours: tuple = (0.0, 1.0, 2.0, 3.0)  # none|low|moderate|high|very_high
    evening_screen_tier_labels: tuple = ("none", "low", "moderate", "high", "very_high")
    last_meal_tier_hours: tuple = (20.0, 21.0, 22.0, 23.0)  # before 8pm .. after 11pm
    last_meal_tier_labels: tuple = (
        "before_8pm",
        "8_9pm",
        "9_10pm",
        "10_11pm",
        "after_11pm",
    )

    # --- Physiology (non-causal, Version 1) ---
    resting_hr_mean_bpm: float = 62.0
    resting_hr_sd_bpm: float = 7.0
    hrv_mean_ms: float = 55.0
    hrv_sd_ms: float = 15.0
    wrist_temp_mean_c: float = 33.5
    wrist_temp_sd_c: float = 0.4

    # --- Scheduling ---
    # Saturday/Sunday treated as free days; a common simplification, not
    # a claim about any individual participant's real work schedule.
    free_day_weekday_indices: tuple = (5, 6)  # Mon=0 ... Sun=6


@dataclass(frozen=True)
class SimulationRunConfig:
    """Parameters for one generator run (population size, span, seed)."""

    num_participants: int = 1000
    num_days: int = 30
    window_size_days: int = 6
    seed: int = 42
    generator_version: str = "1.0.0"
    config_version: str = "1.0.0"
    start_date_iso: str = "2026-01-05"  # a Monday, for readable weekday/weekend alignment


DEFAULT_SOURCE_BACKED = SourceBackedAssumptions()
DEFAULT_SYNTHETIC = SyntheticAssumptions()
DEFAULT_RUN_CONFIG = SimulationRunConfig()

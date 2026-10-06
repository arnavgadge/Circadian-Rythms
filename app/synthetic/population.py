"""Static, per-participant characteristic generation.

Everything in this module runs once per participant, at "onboarding"
(day 0), before any of the 30 days of behavior are simulated. Nothing
here changes as the simulation progresses -- chronotype, MEQ, and the
personality assignment are fixed traits; intrinsic/adapted/current
DLMO are only *initialized* here, then evolved day-by-day by
:mod:`app.synthetic.dlmo_state`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.synthetic.config import SourceBackedAssumptions, SyntheticAssumptions
from app.synthetic.personalities import PERSONALITY_PROFILES
from app.synthetic.rng import RandomStreams
from app.synthetic.time_utils import add_hours, normalize_hour

# Standard Horne & Ostberg (1976) MEQ scoring bands for the 19-item MEQ
# instrument. This is a property of the published instrument, not a
# project-specific or synthetic choice.
MEQ_CATEGORY_BANDS = (
    (16, 30, "definite_evening"),
    (31, 41, "moderate_evening"),
    (42, 58, "intermediate"),
    (59, 69, "moderate_morning"),
    (70, 86, "definite_morning"),
)

# MEQ-by-chronotype target means/SDs: a synthetic mapping (no project
# source gives per-chronotype MEQ means), chosen only so that "early"
# participants trend toward the morning-type end of the real 16-86
# scale and "late" participants trend toward the evening-type end.
_MEQ_MEAN_BY_CHRONOTYPE = {"early": 68.0, "intermediate": 50.0, "late": 32.0}
_MEQ_SD_BY_CHRONOTYPE = {"early": 8.0, "intermediate": 9.0, "late": 8.0}

CHRONOTYPES = ("early", "intermediate", "late")


@dataclass(frozen=True)
class ParticipantTraits:
    """Stable, non-evolving characteristics assigned once per participant."""

    index: int
    participant_code: str
    chronotype: str
    personality_key: str
    meq_score: int
    meq_category: str

    intrinsic_dlmo_hour: float
    initial_adapted_dlmo_hour: float
    initial_current_dlmo_hour: float

    baseline_sleep_onset_hour: float

    light_sensitivity: float
    screen_sensitivity: float
    meal_sensitivity: float


def _meq_category(score: int) -> str:
    for low, high, label in MEQ_CATEGORY_BANDS:
        if low <= score <= high:
            return label
    return "intermediate"


def _stratified_assignment(proportions: dict, n: int, rng: np.random.Generator) -> list:
    """Assign exactly ``n`` labels matching ``proportions`` as closely as
    integer counts allow (largest-remainder rounding), then shuffle.

    Using exact stratified counts rather than independent per-participant
    categorical draws means the realized population distribution matches
    the configured proportions exactly whenever ``n`` divides evenly
    (e.g. 1,000 participants at the default 8/10/25/12/15/18/12% split),
    and as closely as integer rounding allows otherwise -- rather than
    being merely "approximately right" due to sampling noise.
    """

    keys = list(proportions.keys())
    raw_counts = {k: proportions[k] * n for k in keys}
    base_counts = {k: int(np.floor(v)) for k, v in raw_counts.items()}
    remainder = n - sum(base_counts.values())

    remainders = sorted(keys, key=lambda k: raw_counts[k] - base_counts[k], reverse=True)
    for k in remainders[:remainder]:
        base_counts[k] += 1

    labels = []
    for k in keys:
        labels.extend([k] * base_counts[k])

    order = rng.permutation(len(labels))
    return [labels[i] for i in order]


def generate_participants(
    num_participants: int,
    streams: RandomStreams,
    source: SourceBackedAssumptions,
    synthetic: SyntheticAssumptions,
) -> list[ParticipantTraits]:
    """Generate ``num_participants`` participants with stable traits.

    Random draws use the ``population``, ``personality``, and
    ``sensitivity`` streams; chronotype and personality are assigned via
    exact stratified sampling (see :func:`_stratified_assignment`), while
    the continuous traits (DLMO, MEQ, sensitivities) are drawn
    per-participant so each participant's values are independent of
    processing order.
    """

    population_stream = streams["population"]

    chronotypes = _stratified_assignment(
        source.chronotype_population_proportions, num_participants, population_stream
    )
    personalities = _stratified_assignment(
        synthetic.personality_proportions, num_participants, population_stream
    )

    participants: list[ParticipantTraits] = []
    for i in range(num_participants):
        chronotype = chronotypes[i]
        personality_key = personalities[i]

        pop_rng = streams.participant_stream(i, "population")
        sens_rng = streams.participant_stream(i, "sensitivity")

        intrinsic_dlmo_hour = normalize_hour(
            float(
                pop_rng.normal(
                    source.dlmo_mean_hour_by_chronotype[chronotype],
                    source.dlmo_sd_hours_by_chronotype[chronotype],
                )
            )
        )

        # Current/adapted start close to intrinsic at onboarding, with a
        # small independent participant-specific nudge (synthetic).
        initial_adapted_dlmo_hour = normalize_hour(
            intrinsic_dlmo_hour + float(pop_rng.normal(0.0, 0.10))
        )
        initial_current_dlmo_hour = normalize_hour(
            initial_adapted_dlmo_hour + float(pop_rng.normal(0.0, 0.10))
        )

        meq_raw = pop_rng.normal(
            _MEQ_MEAN_BY_CHRONOTYPE[chronotype], _MEQ_SD_BY_CHRONOTYPE[chronotype]
        )
        meq_score = int(
            np.clip(round(meq_raw), source.meq_score_min, source.meq_score_max)
        )

        baseline_sleep_onset_hour = normalize_hour(
            add_hours(intrinsic_dlmo_hour, source.sleep_onset_after_dlmo_hours)
            + float(pop_rng.normal(0.0, source.sleep_onset_dlmo_noise_sd_hours * 0.5))
        )

        light_sensitivity = float(
            np.clip(
                sens_rng.normal(synthetic.light_sensitivity_mean, synthetic.light_sensitivity_sd),
                *synthetic.sensitivity_clip_range,
            )
        )
        screen_sensitivity = float(
            np.clip(
                sens_rng.normal(synthetic.screen_sensitivity_mean, synthetic.screen_sensitivity_sd),
                *synthetic.sensitivity_clip_range,
            )
        )
        meal_sensitivity = float(
            np.clip(
                sens_rng.normal(synthetic.meal_sensitivity_mean, synthetic.meal_sensitivity_sd),
                *synthetic.sensitivity_clip_range,
            )
        )

        participants.append(
            ParticipantTraits(
                index=i,
                participant_code=f"SYN-{i + 1:06d}",
                chronotype=chronotype,
                personality_key=personality_key,
                meq_score=meq_score,
                meq_category=_meq_category(meq_score),
                intrinsic_dlmo_hour=intrinsic_dlmo_hour,
                initial_adapted_dlmo_hour=initial_adapted_dlmo_hour,
                initial_current_dlmo_hour=initial_current_dlmo_hour,
                baseline_sleep_onset_hour=baseline_sleep_onset_hour,
                light_sensitivity=light_sensitivity,
                screen_sensitivity=screen_sensitivity,
                meal_sensitivity=meal_sensitivity,
            )
        )

    return participants


def is_late_habitual_sleeper(
    baseline_sleep_onset_hour: float, synthetic: SyntheticAssumptions
) -> bool:
    """Whether a participant's stable baseline sleep onset counts as "late"
    for the purposes of the late-sleeper/late-meal interaction effect.

    Kept here only as a stable import path for existing callers; the
    actual (single, authoritative) implementation now lives in
    ``app.state.behavioral_effect`` (Phase 6), which both this
    generator's behavioral-effect model and the state engine use, so
    the two can never silently disagree about the definition.
    """

    from app.state.behavioral_effect import is_late_habitual_sleeper as _canonical

    return _canonical(baseline_sleep_onset_hour, synthetic)


def personality_profile(key: str):
    return PERSONALITY_PROFILES[key]

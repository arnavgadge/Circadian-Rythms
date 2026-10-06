"""Translating ``participant_profiles`` + ``daily_observations`` rows
into the Phase 6 state engine's own input types.

``app.state.db_adapter.traits_from_participant_profile`` already does
most of this, but explicitly requires the caller to supply
``baseline_sleep_onset_hour`` and the three behavioral sensitivities,
since those are Phase 3 synthetic-generation concepts, not real
schema columns (see that function's docstring). This module supplies
them from wherever they are actually available for a given
participant, documenting the fallback used when they are not.
"""

from __future__ import annotations

import statistics
from typing import Optional, Sequence

from app.database.models import DailyObservation, ParticipantProfile
from app.pipeline.config import DEFAULT_PIPELINE_CONFIG, PipelineConfig
from app.state.circadian_state import CircadianState, ParticipantPhaseTraits
from app.state.db_adapter import state_from_participant_profile, traits_from_participant_profile
from app.synthetic.time_utils import add_hours, circular_mean_hours, clock_time_to_hour


def _mean_sleep_onset_hour(window_observations: Sequence[DailyObservation]) -> Optional[float]:
    hours = [clock_time_to_hour(o.sleep_onset_time) for o in window_observations if o.sleep_onset_time is not None]
    if not hours:
        return None
    return circular_mean_hours(hours)


def build_participant_traits(
    profile: ParticipantProfile,
    window_observations: Sequence[DailyObservation],
    config: PipelineConfig = DEFAULT_PIPELINE_CONFIG,
) -> ParticipantPhaseTraits:
    """``baseline_sleep_onset_hour``: for a synthetic participant this
    would ideally be the Phase 3 generation trait, but that value is
    not persisted anywhere in the Phase 2 schema (only the three
    sensitivities and a personality label are, in
    ``synthetic_personality_profile``). The mean of the participant's
    own recent observed sleep onset is used as an empirical proxy
    instead -- documented here as a **production approximation**, not
    a recovered ground-truth trait. If no sleep-onset observations are
    available at all, falls back to the intrinsic DLMO plus a fixed
    configured offset (the same +2h "ideal sleep after DLMO" convention
    Phase 8's alignment engine documents as its own project
    assumption).
    """

    if profile.intrinsic_dlmo_time is None:
        # A freshly onboarded (e.g. via the Phase 15 API) participant
        # has no intrinsic DLMO yet -- no phase computes one from
        # questionnaire data alone (see app.api.services.participant_service).
        # Fail cleanly here so the orchestrator's existing ValueError
        # handling (stage="traits") reports this, rather than an
        # unguarded AttributeError further down.
        raise ValueError("participant_profiles.intrinsic_dlmo_time is required to build participant traits")

    synthetic_profile = profile.synthetic_personality_profile or {}

    baseline_sleep_onset_hour = _mean_sleep_onset_hour(window_observations)
    intrinsic_hour = clock_time_to_hour(profile.intrinsic_dlmo_time)
    if baseline_sleep_onset_hour is None:
        baseline_sleep_onset_hour = add_hours(intrinsic_hour, config.baseline_sleep_onset_fallback_offset_hours)

    return traits_from_participant_profile(
        profile,
        baseline_sleep_onset_hour=baseline_sleep_onset_hour,
        light_sensitivity=synthetic_profile.get("light_sensitivity", config.default_sensitivity),
        screen_sensitivity=synthetic_profile.get("screen_sensitivity", config.default_sensitivity),
        meal_sensitivity=synthetic_profile.get("meal_sensitivity", config.default_sensitivity),
    )


def build_previous_state(profile: ParticipantProfile) -> Optional[CircadianState]:
    """``None`` if the profile has never been initialized (true Day-0
    onboarding, before any state exists) -- the caller is expected to
    call ``app.state.engine.initialize_state`` itself in that case,
    since that decision belongs to the pipeline's onboarding-schedule
    logic, not this translation helper."""

    try:
        return state_from_participant_profile(profile)
    except ValueError:
        return None

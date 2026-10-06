"""The state engine's core data types.

``CircadianState`` is intentionally minimal for what a caller needs to
carry forward day-to-day; the optional debug/audit fields (populated
by :func:`app.state.engine.step`, never required for the next day's
transition) are kept on a separate :class:`StateTransitionDebug`
object so nothing forces debugging data into whatever a caller
persists.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional

from app.state.behavioral_effect import BehavioralEffect


@dataclass(frozen=True)
class ParticipantPhaseTraits:
    """The minimal, stable per-participant traits the state engine needs.

    Deliberately independent of ``app.synthetic.population.
    ParticipantTraits`` -- the state engine must not depend on the
    synthetic-generation package; callers (Phase 3's compatibility
    layer, a future production adapter) translate their own richer
    participant representation into this at the call site.
    """

    intrinsic_dlmo_hour: float
    baseline_sleep_onset_hour: float
    light_sensitivity: float = 1.0
    screen_sensitivity: float = 1.0
    meal_sensitivity: float = 1.0
    chronotype: Optional[str] = None


@dataclass(frozen=True)
class CircadianState:
    """The three-layer circadian state for one participant on one day."""

    intrinsic_dlmo_hour: float
    adapted_dlmo_hour: float
    current_dlmo_hour: float
    chronotype: Optional[str] = None
    date: Optional[date_cls] = None


@dataclass(frozen=True)
class StateTransitionDebug:
    """Optional audit/debug detail produced by one call to
    :func:`app.state.engine.step`. Not required by the next day's
    transition and not forced into database storage."""

    behavioral_effect: BehavioralEffect
    behavioral_equilibrium_hour: float
    raw_adapted_delta_hours: float
    raw_current_delta_hours: float
    current_pull_to_adapted_hours: float
    current_state_noise_hours: float
    unclamped_current_delta_hours: float
    continuity_cap_applied: bool

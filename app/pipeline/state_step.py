"""STEP 8 of the daily pipeline: run the Phase 6 state engine.

Never calls XGBoost and never touches the database itself -- only
``app.state.engine.step`` / ``initialize_state`` and the existing
``app.state.db_adapter`` / ``app.state.behavioral_effect`` translation
helpers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional, Sequence

from app.database.models import DailyObservation
from app.state.db_adapter import behavior_inputs_from_daily_observation
from app.state.circadian_state import CircadianState, ParticipantPhaseTraits
from app.state.config import DEFAULT_STATE_ENGINE_CONFIG, StateEngineConfig
from app.state.engine import initialize_state, step


@dataclass(frozen=True)
class StateStepResult:
    new_state: CircadianState
    debug: Optional[object]  # StateTransitionDebug, if a real transition ran
    was_initialized: bool  # True Day-0 onboarding: no prior state existed
    was_updated: bool  # a real behavioral transition was applied
    reason: str


def run_state_step(
    previous_state: Optional[CircadianState],
    window_observations: Sequence[DailyObservation],
    traits: ParticipantPhaseTraits,
    target_date: date_cls,
    config: StateEngineConfig = DEFAULT_STATE_ENGINE_CONFIG,
) -> StateStepResult:
    if previous_state is None:
        # True Day-0 onboarding: no prior authoritative state exists at
        # all yet (see docs "Start-of-day timing" / Q23 schedule).
        new_state = initialize_state(traits.intrinsic_dlmo_hour, chronotype=traits.chronotype, config=config, date=target_date)
        return StateStepResult(new_state, None, True, True, "initialized (no prior state)")

    if not window_observations:
        return StateStepResult(previous_state, None, False, False, "no behavior available; state carried forward unchanged")

    behavior = behavior_inputs_from_daily_observation(window_observations[-1])
    if behavior is None:
        return StateStepResult(
            previous_state, None, False, False, "most recent day's behavior incomplete; state carried forward unchanged"
        )

    new_state, debug = step(previous_state, behavior, traits, config=config, date=target_date)
    return StateStepResult(new_state, debug, False, True, "stepped forward one day")

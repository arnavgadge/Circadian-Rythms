"""State trajectory replay.

Given a participant's initialization and an ordered sequence of daily
behavior inputs, reproduces the full ``intrinsic``/``adapted``/
``current`` DLMO trajectory -- deterministically, with no dependency on
Phase 3's generator module. This is both a general-purpose utility
(a future production system can replay a participant's history to
recompute/verify their current state) and the mechanism
``tests/test_state_replay.py`` uses to confirm this engine reproduces
Phase 3's historical synthetic trajectories exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_cls
from typing import Optional, Sequence

from app.state.behavioral_effect import DailyBehaviorInputs
from app.state.circadian_state import CircadianState, ParticipantPhaseTraits, StateTransitionDebug
from app.state.config import DEFAULT_STATE_ENGINE_CONFIG, StateEngineConfig
from app.state.engine import initialize_state, step
from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SourceBackedAssumptions, SyntheticAssumptions


@dataclass(frozen=True)
class ReplayDay:
    """One day's result within a replayed trajectory."""

    date: Optional[date_cls]
    state: CircadianState
    debug: StateTransitionDebug


def replay_trajectory(
    traits: ParticipantPhaseTraits,
    daily_behaviors: Sequence[DailyBehaviorInputs],
    dates: Optional[Sequence[date_cls]] = None,
    config: StateEngineConfig = DEFAULT_STATE_ENGINE_CONFIG,
    source: SourceBackedAssumptions = DEFAULT_SOURCE_BACKED,
    synthetic: SyntheticAssumptions = DEFAULT_SYNTHETIC,
    apply_continuity_cap: bool = True,
) -> list:
    """Replay a full trajectory from onboarding through ``len(daily_behaviors)`` days.

    Returns a list of :class:`ReplayDay`, one per input day, in order.
    The initial (day-0) state is *not* included in the returned list --
    it is only the starting point for day 1's transition -- matching
    how the Phase 3 simulator's own daily loop is structured (day
    indices 0..N-1 each produce one stored state).

    Purely deterministic: no randomness is introduced here. Pass
    ``apply_continuity_cap=False`` to reproduce a Phase 3 trajectory
    exactly (see ``app.synthetic.dlmo_state`` and
    ``docs/state_engine.md`` "Relationship to Phase 3").
    """

    if dates is not None and len(dates) != len(daily_behaviors):
        raise ValueError("dates, when given, must have the same length as daily_behaviors")

    state = initialize_state(traits.intrinsic_dlmo_hour, traits.chronotype, config)
    results: list = []

    for i, behavior in enumerate(daily_behaviors):
        day_date = dates[i] if dates is not None else None
        state, debug = step(
            previous_state=state,
            behavior=behavior,
            traits=traits,
            config=config,
            source=source,
            synthetic=synthetic,
            apply_continuity_cap=apply_continuity_cap,
            date=day_date,
        )
        results.append(ReplayDay(date=day_date, state=state, debug=debug))

    return results

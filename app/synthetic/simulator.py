"""Top-level orchestration: population -> behavior -> biological state -> tables.

For each participant, in isolation from every other participant:

1. generate stable characteristics (:mod:`app.synthetic.population`)
2. initialize ``intrinsic``/``adapted``/``current`` DLMO
3. walk through the 30 days *in order*, each day:
   a. generate that day's behavior independently
      (:mod:`app.synthetic.behavior`)
   b. advance the biological state by exactly one day
      (:mod:`app.synthetic.dlmo_state.step`), using the *previous*
      day's state as input
4. record every day's raw observations and the resulting state

The output is three pandas DataFrames (participants, daily records,
sliding-window metadata) -- convenient for validation, diagnostics,
export, and database writing, but SQL remains the authoritative store
once :mod:`app.synthetic.db_writer` has run.

**Temporal ordering, explicitly**: the value stored as "day N's target
DLMO" is the ``current_DLMO`` state produced by applying day N's state
transition -- i.e. it reflects day N's behavior having already acted on
the state. A window's target date is the day *after* its 6-day feature
span (days N-6..N-1 -> target day N), so day N's own behavior is never
part of its own target's feature window; only days strictly before the
target date are. This is what prevents target leakage. See
``docs/synthetic_data_generation.md`` section 12 for the full
walk-through.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone

import pandas as pd

from app.synthetic.behavior import generate_daily_behavior
from app.synthetic.config import (
    DEFAULT_RUN_CONFIG,
    DEFAULT_SOURCE_BACKED,
    DEFAULT_SYNTHETIC,
    SimulationRunConfig,
    SourceBackedAssumptions,
    SyntheticAssumptions,
)
from app.synthetic.dlmo_state import DLMOState, step
from app.synthetic.personalities import PERSONALITY_PROFILES
from app.synthetic.population import generate_participants
from app.synthetic.rng import RandomStreams
from app.synthetic.time_utils import circular_mean_hours


@dataclass
class SyntheticDataset:
    participants_df: pd.DataFrame
    daily_df: pd.DataFrame
    windows_df: pd.DataFrame
    run_config: SimulationRunConfig
    generated_at: datetime


def generate_synthetic_dataset(
    run_config: SimulationRunConfig = DEFAULT_RUN_CONFIG,
    source: SourceBackedAssumptions = DEFAULT_SOURCE_BACKED,
    synthetic: SyntheticAssumptions = DEFAULT_SYNTHETIC,
) -> SyntheticDataset:
    streams = RandomStreams(run_config.seed)
    participants = generate_participants(run_config.num_participants, streams, source, synthetic)
    start_date = date_cls.fromisoformat(run_config.start_date_iso)

    participant_rows: list[dict] = []
    daily_rows: list[dict] = []

    for p in participants:
        personality = PERSONALITY_PROFILES[p.personality_key]
        state = DLMOState(
            intrinsic_hour=p.intrinsic_dlmo_hour,
            adapted_hour=p.initial_adapted_dlmo_hour,
            current_hour=p.initial_current_dlmo_hour,
        )

        behavior_rng = streams.participant_stream(p.index, "behavior")
        disruption_rng = streams.participant_stream(p.index, "disruption")
        physiology_rng = streams.participant_stream(p.index, "physiology")
        state_rng = streams.participant_stream(p.index, "state")

        previous_midpoint = None
        free_day_midpoints: list[float] = []

        for day_index in range(run_config.num_days):
            date_obj = start_date + timedelta(days=day_index)

            behavior = generate_daily_behavior(
                participant=p,
                personality=personality,
                day_index=day_index,
                date_obj=date_obj,
                behavior_rng=behavior_rng,
                disruption_rng=disruption_rng,
                physiology_rng=physiology_rng,
                synthetic=synthetic,
                previous_sleep_midpoint_hour=previous_midpoint,
            )

            new_state, effect = step(state, behavior, p, source, synthetic, state_rng)

            if behavior.is_free_day and behavior.free_day_sleep_midpoint_hour is not None:
                free_day_midpoints.append(behavior.free_day_sleep_midpoint_hour)

            row = asdict(behavior)
            row.update(
                participant_index=p.index,
                participant_code=p.participant_code,
                previous_current_dlmo_hour=state.current_hour,
                adapted_dlmo_hour=new_state.adapted_hour,
                current_dlmo_hour=new_state.current_hour,
                intrinsic_dlmo_hour=new_state.intrinsic_hour,
                light_effect_minutes=effect.light_effect_minutes,
                screen_effect_minutes=effect.screen_effect_minutes,
                meal_effect_minutes=effect.meal_effect_minutes,
                exercise_effect_minutes=effect.exercise_effect_minutes,
                caffeine_effect_minutes=effect.caffeine_effect_minutes,
                noise_minutes=effect.noise_minutes,
                clipped_total_shift_minutes=effect.clipped_total_minutes,
                morning_light_tier=effect.morning_light_tier,
                evening_screen_tier=effect.evening_screen_tier,
                last_meal_tier=effect.last_meal_tier,
            )
            daily_rows.append(row)

            state = new_state
            previous_midpoint = behavior.sleep_midpoint_hour

        msfsc_baseline_hour = (
            circular_mean_hours(free_day_midpoints) if free_day_midpoints else None
        )

        participant_row = asdict(p)
        participant_row.update(
            final_adapted_dlmo_hour=state.adapted_hour,
            final_current_dlmo_hour=state.current_hour,
            msfsc_baseline_hour=msfsc_baseline_hour,
            num_free_days_observed=len(free_day_midpoints),
        )
        participant_rows.append(participant_row)

    participants_df = pd.DataFrame(participant_rows)
    daily_df = pd.DataFrame(daily_rows)
    windows_df = _build_windows(daily_df, run_config)

    return SyntheticDataset(
        participants_df=participants_df,
        daily_df=daily_df,
        windows_df=windows_df,
        run_config=run_config,
        generated_at=datetime.now(timezone.utc),
    )


def _build_windows(daily_df: pd.DataFrame, run_config: SimulationRunConfig) -> pd.DataFrame:
    """Build the sliding-window metadata table.

    For a 30-day span and a 6-day window, this produces exactly
    ``30 - 6 = 24`` windows per participant: days 1-6 -> target day 7,
    days 2-7 -> target day 8, ..., days 24-29 -> target day 30 (using
    1-based day numbering; 0-based internally).
    """

    window_size = run_config.window_size_days
    num_days = run_config.num_days

    lookup = daily_df.set_index(["participant_index", "day_index"])

    rows: list[dict] = []
    for participant_index, group in daily_df.groupby("participant_index"):
        dates_by_day = group.set_index("day_index")["date"]
        participant_code = group["participant_code"].iloc[0]

        for window_index, start_day in enumerate(range(0, num_days - window_size), start=1):
            end_day = start_day + window_size - 1
            target_day = start_day + window_size

            target_row = lookup.loc[(participant_index, target_day)]

            rows.append(
                {
                    "participant_index": participant_index,
                    "participant_code": participant_code,
                    "window_index": window_index,
                    "feature_start_date": dates_by_day.loc[start_day],
                    "feature_end_date": dates_by_day.loc[end_day],
                    "feature_start_day_index": start_day,
                    "feature_end_day_index": end_day,
                    "target_date": dates_by_day.loc[target_day],
                    "target_day_index": target_day,
                    # Denormalized for inspection convenience only; the
                    # database's circadian_labels rows remain authoritative.
                    "target_current_dlmo_hour": target_row["current_dlmo_hour"],
                }
            )

    return pd.DataFrame(rows)

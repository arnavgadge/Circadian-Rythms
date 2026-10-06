"""Baseline/intervention period selection and intervention-episode
detection.

An "episode" is a run of consecutive ``intervention_log`` days with
the **same** ``recommendation_id`` -- since Phase 10/11 may switch the
primary recommendation day to day, a participant's log is not one
continuous intervention but a sequence of episodes that must be kept
distinct (see ``docs/intervention_effectiveness.md`` "Intervention
lifecycle").
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date as date_cls, timedelta
from typing import Optional, Sequence

from app.effectiveness.config import DEFAULT_EFFECTIVENESS_CONFIG, EffectivenessConfig

INSUFFICIENT_BASELINE_HISTORY = "insufficient_baseline_history"
INSUFFICIENT_INTERVENTION_HISTORY = "insufficient_intervention_history"


@dataclass(frozen=True)
class InterventionEpisode:
    recommendation_id: int
    start_date: date_cls
    end_date: date_cls
    log_dates: tuple  # every date logged within the episode, ascending


@dataclass(frozen=True)
class Period:
    start_date: date_cls
    end_date: date_cls
    observed_dates: tuple  # dates within [start_date, end_date] that actually have data
    requested_days: int

    @property
    def completeness(self) -> float:
        return len(self.observed_dates) / self.requested_days if self.requested_days else 0.0


def detect_episodes(log_rows: Sequence) -> list:
    """``log_rows``: any objects with ``.log_date`` and
    ``.recommendation_id``, sorted ascending by date (the caller is
    expected to have queried them that way -- this function does not
    re-sort, so it can also be used incrementally).

    A new episode starts whenever ``recommendation_id`` changes **or**
    a date gap breaks consecutiveness -- the same intervention
    recommended, dropped, and recommended again weeks later is two
    separate episodes, not one continuous one."""

    episodes: list = []
    current_id = None
    current_dates: list = []

    def _flush():
        if current_id is not None and current_dates:
            episodes.append(InterventionEpisode(current_id, current_dates[0], current_dates[-1], tuple(current_dates)))

    for row in log_rows:
        starts_new_episode = (
            row.recommendation_id != current_id
            or (current_dates and row.log_date != current_dates[-1] + timedelta(days=1))
        )
        if starts_new_episode:
            _flush()
            current_id = row.recommendation_id
            current_dates = [row.log_date]
        else:
            current_dates.append(row.log_date)
    _flush()
    return episodes


def select_baseline_window(
    episode_start: date_cls, available_dates: set, config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG
) -> Optional[Period]:
    """The ``baseline_window_days`` days immediately before
    ``episode_start`` -- never a future date relative to the
    intervention, and never fabricated for a day with no data."""

    requested = config.baseline_window_days
    candidate_dates = [episode_start - timedelta(days=i) for i in range(requested, 0, -1)]
    observed = tuple(d for d in candidate_dates if d in available_dates)

    period = Period(candidate_dates[0], candidate_dates[-1], observed, requested)
    if period.completeness < config.min_window_completeness:
        return None
    return period


def select_intervention_window(
    episode: InterventionEpisode,
    available_dates: set,
    config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG,
) -> Optional[Period]:
    """The most recent ``intervention_window_days`` days of the episode
    (or the whole episode if shorter) -- never a single day treated as
    a reliable effect."""

    requested = config.intervention_window_days
    window_dates = list(episode.log_dates[-requested:])
    observed = tuple(d for d in window_dates if d in available_dates)

    period = Period(window_dates[0], window_dates[-1], observed, len(window_dates))
    min_days_needed = math.ceil(requested * config.min_window_completeness)
    if len(episode.log_dates) < min_days_needed or period.completeness < config.min_window_completeness:
        return None
    return period

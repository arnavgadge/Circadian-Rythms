"""Cooldown / repetition handling for the currently-active primary
intervention.

Not a medical treatment schedule -- a simple, configurable adherence
heuristic: don't switch the participant's primary focus every single
day. If the same intervention was already primary within
``RecommendationConfig.primary_cooldown_days`` and is not scoring
outright badly, give it a small continuation bonus so a marginally
higher-scoring alternative doesn't needlessly displace it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from app.recommendations.config import DEFAULT_RECOMMENDATION_CONFIG, RecommendationConfig


@dataclass(frozen=True)
class PriorPrimary:
    intervention_id: int
    log_date: date


def continuation_bonus_for(
    intervention_id: int,
    prior_primary: Optional[PriorPrimary],
    today: date,
    config: RecommendationConfig = DEFAULT_RECOMMENDATION_CONFIG,
) -> float:
    """0.0 unless ``intervention_id`` was the primary within the cooldown
    window, in which case the configured continuation bonus."""

    if prior_primary is None or prior_primary.intervention_id != intervention_id:
        return 0.0
    days_since = (today - prior_primary.log_date).days
    if 0 <= days_since <= config.primary_cooldown_days:
        return config.continuation_bonus
    return 0.0


def should_continue_prior_primary(
    prior_primary_score: Optional[float],
    best_candidate_score: float,
    config: RecommendationConfig = DEFAULT_RECOMMENDATION_CONFIG,
) -> bool:
    """Even with its continuation bonus already folded into
    ``prior_primary_score``, a prior primary that has fallen far behind
    the best alternative is still replaced -- cooldown favors stability,
    not stubbornness."""

    if prior_primary_score is None:
        return False
    if best_candidate_score <= 0:
        return prior_primary_score >= best_candidate_score
    return (prior_primary_score / best_candidate_score) >= config.continuation_minimum_relative_score

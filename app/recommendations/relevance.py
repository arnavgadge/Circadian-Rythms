"""Contributor relevance: how strongly a candidate intervention targets
what Phase 9 identified as *this participant's* actual problem, rather
than a generically high-literature-impact behavior unrelated to them.

An intervention whose ``contributor_signals`` includes one of the
participant's top-3 ranked, *significant* contributors gets a
relevance score keyed by that contributor's rank
(``RecommendationConfig.relevance_by_rank``); an intervention
addressing more than one such contributor gets a small consolidation
bonus rather than being penalized for "trying to do too much" --
preferred over recommending two near-duplicate actions (see
``docs/recommendation_engine.md`` "Conflict resolution").
"""

from __future__ import annotations

from dataclasses import dataclass

from app.recommendations.config import DEFAULT_RECOMMENDATION_CONFIG, RecommendationConfig


@dataclass(frozen=True)
class RelevanceResult:
    relevance: float  # 0-1
    matched_signals: tuple  # the participant's significant top-3 signals this candidate addresses


def compute_contributor_relevance(
    contributor_signals: tuple,
    ranked_significant_signals: tuple,  # e.g. ("evening_screen", "social_jetlag") in rank order
    config: RecommendationConfig = DEFAULT_RECOMMENDATION_CONFIG,
) -> RelevanceResult:
    matched = []
    relevance = 0.0

    for rank, signal in enumerate(ranked_significant_signals):
        if signal in contributor_signals:
            matched.append(signal)
            weight = config.relevance_by_rank[rank] if rank < len(config.relevance_by_rank) else 0.0
            relevance = max(relevance, weight)

    if len(matched) > 1:
        relevance = min(1.0, relevance + config.multi_signal_relevance_bonus)

    return RelevanceResult(relevance=relevance, matched_signals=tuple(matched))

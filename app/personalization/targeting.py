"""Personalized graduated-target aggressiveness -- an optional, bounded
adjustment to Phase 10's ~50% graduated-target fraction, never a
replacement for it and never able to remove Phase 10's own
feasibility/bounds constraints (see
``docs/personalization_engine.md`` "Intervention targeting").

This is exposed as a pure function a future integration point can call
to build a per-call ``RecommendationConfig(graduated_target_fraction=...)``;
Phase 13 does not itself construct or pass that config into Phase 10,
keeping the two loosely coupled (see dispatcher module docstring).
"""

from __future__ import annotations

from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG, PersonalizationConfig
from app.recommendations.personalization import ADAPTIVE_POLICY, LITERATURE, PERSONAL_EFFECT, PERSONAL_RANKING


def adjust_target_aggressiveness(
    base_fraction: float,
    personalization_phase: str,
    model_validity_score: float = 0.0,  # 0.0 (no adjustment) .. 1.0 (full configured adjustment), caller-supplied
    config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG,
) -> float:
    """Only ``PERSONAL_EFFECT``/``ADAPTIVE_POLICY`` (real personal
    evidence) may adjust aggressiveness at all, and only within
    ``max_target_aggressiveness_adjustment`` either direction --
    ``LITERATURE``/``PERSONAL_RANKING`` always return ``base_fraction``
    unchanged."""

    if personalization_phase not in (PERSONAL_EFFECT, ADAPTIVE_POLICY):
        return base_fraction

    bounded_score = max(-1.0, min(1.0, model_validity_score))
    adjustment = bounded_score * config.max_target_aggressiveness_adjustment
    return max(0.05, min(0.95, base_fraction + adjustment))

"""Personalization-phase compatibility.

This phase does **not** implement personal-effect learning or a
contextual bandit -- both belong to a later phase (Q28). What it does
implement is the *interface* those phases will plug into, so they can
supply already-computed scores/effects without the core engine being
rewritten:

- ``LITERATURE`` (default): the catalogue's own
  ``literature_expected_improvement_minutes`` is used as-is, and no
  score adjustment is applied.
- ``PERSONAL_RANKING``: the caller supplies an externally computed
  per-intervention ranking score (``personalized_ranking``); it is
  blended additively into the candidate score, but the *stated*
  expected improvement stays literature-sourced (only the ordering is
  personalized, not the claimed effect size).
- ``PERSONAL_EFFECT``: the caller supplies an externally computed
  per-intervention expected improvement (``personal_expected_improvement``),
  which replaces (or, if
  ``RecommendationConfig.blend_personal_and_literature``, averages
  with) the literature value.
- ``ADAPTIVE_POLICY``: reserved for a future contextual-bandit phase.
  Accepted as a valid phase value for forward interface compatibility
  only; this phase's behavior for it is identical to ``LITERATURE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.recommendations.config import DEFAULT_RECOMMENDATION_CONFIG, RecommendationConfig

LITERATURE = "literature"
PERSONAL_RANKING = "personal_ranking"
PERSONAL_EFFECT = "personal_effect"
ADAPTIVE_POLICY = "adaptive_policy"

VALID_PHASES = (LITERATURE, PERSONAL_RANKING, PERSONAL_EFFECT, ADAPTIVE_POLICY)

SOURCE_LITERATURE = "literature"
SOURCE_PERSONAL = "personal"
SOURCE_BLENDED = "blended"


@dataclass(frozen=True)
class PersonalizationResult:
    expected_improvement_minutes: Optional[float]
    expected_improvement_source: str  # "literature" | "personal" | "blended"
    score_adjustment: float  # additive term folded into the candidate score


def resolve_expected_improvement(
    intervention_id: int,
    literature_expected_improvement_minutes: Optional[float],
    personalization_phase: str,
    personalized_ranking: Optional[dict] = None,
    personal_expected_improvement: Optional[dict] = None,
    config: RecommendationConfig = DEFAULT_RECOMMENDATION_CONFIG,
) -> PersonalizationResult:
    if personalization_phase not in VALID_PHASES:
        raise ValueError(f"Unknown personalization phase: {personalization_phase}")

    if personalization_phase == PERSONAL_RANKING and personalized_ranking:
        adjustment = float(personalized_ranking.get(intervention_id, 0.0))
        return PersonalizationResult(
            expected_improvement_minutes=literature_expected_improvement_minutes,
            expected_improvement_source=SOURCE_LITERATURE,
            score_adjustment=adjustment,
        )

    if personalization_phase == PERSONAL_EFFECT and personal_expected_improvement:
        personal_value = personal_expected_improvement.get(intervention_id)
        if personal_value is not None:
            if config.blend_personal_and_literature and literature_expected_improvement_minutes is not None:
                blended = (personal_value + literature_expected_improvement_minutes) / 2.0
                return PersonalizationResult(blended, SOURCE_BLENDED, 0.0)
            return PersonalizationResult(personal_value, SOURCE_PERSONAL, 0.0)

    # LITERATURE, ADAPTIVE_POLICY (interface-only), or a personalized
    # phase with no data supplied yet for this intervention -- fall
    # back to the literature value with no adjustment.
    return PersonalizationResult(literature_expected_improvement_minutes, SOURCE_LITERATURE, 0.0)

"""Verifies a recommendation belongs to the approved behavioral
catalogue before it can ever reach a participant-facing output. This
is a defense-in-depth check: Phase 10's catalogue is already
behavioral-only by construction, but if anything reaches this layer
with an unapproved category or medical/clinical language, it is
**blocked outright**, never merely logged and passed through.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.safety.config import DEFAULT_SAFETY_CONFIG, SafetyConfig
from app.safety.messages import PROHIBITED_RECOMMENDATION_TERMS


@dataclass(frozen=True)
class RecommendationSafetyResult:
    is_safe: bool
    reason: Optional[str]


def validate_recommendation_safety(
    intervention_type: Optional[str],
    text: Optional[str],
    config: SafetyConfig = DEFAULT_SAFETY_CONFIG,
) -> RecommendationSafetyResult:
    if intervention_type is None or intervention_type not in config.approved_intervention_types:
        return RecommendationSafetyResult(False, f"intervention_type '{intervention_type}' is not in the approved catalogue")

    lowered = (text or "").lower()
    for term in PROHIBITED_RECOMMENDATION_TERMS:
        if term in lowered:
            return RecommendationSafetyResult(False, f"recommendation text contains prohibited term '{term.strip()}'")

    return RecommendationSafetyResult(True, None)

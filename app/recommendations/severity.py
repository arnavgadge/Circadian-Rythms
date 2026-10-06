"""Misalignment severity classification and severity-specific weighting.

Bands are computed directly from Phase 8's ``final_score`` -- a
**project design choice** (see ``docs/recommendation_engine.md``
"Severity model"), not a clinically validated cutoff. They exist only
to decide how aggressively the recommendation engine should trade off
expected impact against feasibility (section "Severity weights"), not
to make any diagnostic claim about the participant.
"""

from __future__ import annotations

from app.recommendations.config import DEFAULT_RECOMMENDATION_CONFIG, RecommendationConfig, SeverityWeights

GOOD = "good"
MILD = "mild"
MODERATE = "moderate"
SEVERE = "severe"


def classify_severity(alignment_score: float, config: RecommendationConfig = DEFAULT_RECOMMENDATION_CONFIG) -> str:
    if alignment_score >= config.severity_good_threshold:
        return GOOD
    if alignment_score >= config.severity_mild_threshold:
        return MILD
    if alignment_score >= config.severity_moderate_threshold:
        return MODERATE
    return SEVERE


def severity_weights(severity: str, config: RecommendationConfig = DEFAULT_RECOMMENDATION_CONFIG) -> SeverityWeights:
    return {
        GOOD: config.good_weights,
        MILD: config.mild_weights,
        MODERATE: config.moderate_weights,
        SEVERE: config.severe_weights,
    }[severity]

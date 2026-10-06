"""Literature/personal blending -- early personalization should not
abruptly replace the literature value (see
``docs/personalization_engine.md`` "Literature blending").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG, PersonalizationConfig

SOURCE_LITERATURE = "literature"
SOURCE_BLENDED = "blended"
SOURCE_PERSONAL = "personal"


@dataclass(frozen=True)
class BlendedEstimate:
    value: Optional[float]
    source: str


def blend_effect(
    literature_effect: Optional[float],
    personal_effect: Optional[float],
    n_observations: int,
    personal_model_valid: bool,
    config: PersonalizationConfig = DEFAULT_PERSONALIZATION_CONFIG,
) -> BlendedEstimate:
    if personal_effect is None or not personal_model_valid:
        return BlendedEstimate(literature_effect, SOURCE_LITERATURE)

    if n_observations >= config.full_personal_min_observations:
        return BlendedEstimate(personal_effect, SOURCE_PERSONAL)

    if literature_effect is None:
        return BlendedEstimate(personal_effect, SOURCE_PERSONAL)

    blended = config.blended_personal_weight * personal_effect + config.blended_literature_weight * literature_effect
    return BlendedEstimate(blended, SOURCE_BLENDED)

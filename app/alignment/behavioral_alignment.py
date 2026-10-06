"""Behavioral alignment: the weighted combination of the five components."""

from __future__ import annotations

from dataclasses import dataclass

from app.alignment.behavioral_components import (
    compute_evening_screen_score,
    compute_meal_timing_score,
    compute_morning_light_score,
    compute_sleep_consistency_score,
    compute_social_jetlag_score,
)
from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG, AlignmentConfig
from app.alignment.inputs import AlignmentInputs, ComponentScore


@dataclass(frozen=True)
class BehavioralAlignmentResult:
    behavioral_score: float
    components: dict  # name -> ComponentScore


def compute_behavioral_alignment(
    inputs: AlignmentInputs, config: AlignmentConfig = DEFAULT_ALIGNMENT_CONFIG
) -> BehavioralAlignmentResult:
    components: dict = {
        "sleep_consistency": compute_sleep_consistency_score(inputs.window_sleep_onset_hours, config),
        "morning_light": compute_morning_light_score(inputs.window_morning_light_duration_minutes, config),
        "evening_screen": compute_evening_screen_score(inputs.window_evening_screen_duration_hours, config),
        "meal_timing": compute_meal_timing_score(inputs.window_last_meal_hours, config),
        "social_jetlag": compute_social_jetlag_score(inputs.window_social_jetlag_minutes, config),
    }

    weights = {
        "sleep_consistency": config.sleep_consistency_weight,
        "morning_light": config.morning_light_weight,
        "evening_screen": config.evening_screen_weight,
        "meal_timing": config.meal_timing_weight,
        "social_jetlag": config.social_jetlag_weight,
    }

    behavioral_score = sum(components[name].score * weight for name, weight in weights.items())

    return BehavioralAlignmentResult(behavioral_score=behavioral_score, components=components)

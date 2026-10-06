"""Deterministic recommendation-text rendering.

Templates live in the database catalogue (``Recommendation.extra_metadata
["template"]``); this module only fills in ``{variable}`` placeholders
with already-formatted, human-readable strings. No LLM, no free-form
generation -- the same template with the same inputs always renders
the same text.
"""

from __future__ import annotations

from app.recommendations.catalogue import CLOCK_HOUR, DURATION_HOURS, CandidateIntervention
from app.synthetic.time_utils import hour_to_clock_time


def format_clock_hour(hour: float) -> str:
    """``14.5`` -> ``"2:30 PM"``. Never expose a raw float clock hour
    directly in user-facing text."""

    t = hour_to_clock_time(hour)
    suffix = "AM" if t.hour < 12 else "PM"
    hour_12 = t.hour % 12
    if hour_12 == 0:
        hour_12 = 12
    return f"{hour_12}:{t.minute:02d} {suffix}"


def format_duration(value: float, value_kind: str) -> str:
    if value_kind == DURATION_HOURS:
        return f"{value:.1f} hour(s)"
    return f"{value:.0f} minute(s)"


def render_target_value(target_value: float, value_kind: str) -> str:
    if value_kind == CLOCK_HOUR:
        return format_clock_hour(target_value)
    return format_duration(target_value, value_kind)


def render_template(
    candidate: CandidateIntervention,
    target_value: float,
    current_value: float,
    expected_improvement_minutes: float,
) -> str:
    rendered_target = render_target_value(target_value, candidate.value_kind)
    rendered_current = render_target_value(current_value, candidate.value_kind)
    variables = {
        "title": candidate.title,
        "target_time": rendered_target,
        "target_value": rendered_target,
        "current_value": rendered_current,
        "expected_improvement": (
            f"~{abs(expected_improvement_minutes):.0f} min" if expected_improvement_minutes is not None else "unknown"
        ),
    }
    return candidate.template.format_map(_SafeDict(variables))


class _SafeDict(dict):
    """``str.format_map`` helper: leaves an unrecognized ``{placeholder}``
    untouched instead of raising, so a catalogue template referencing a
    field this phase doesn't populate degrades visibly rather than
    crashing the whole selection."""

    def __missing__(self, key):
        return "{" + key + "}"

"""Seed mechanism for static reference/catalogue data.

Only the recommendation catalogue is seeded here: intervention names,
categories, descriptions, and the structured ``extra_metadata`` the
Phase 10 recommendation engine (``app.recommendations``) reads to
compute targets, feasibility, and relevance -- never a second,
Python-hard-coded catalogue. Seeding is idempotent: re-running it does
not duplicate rows.

**Important disclosure**: ``literature_expected_improvement_minutes``
and every numeric field inside ``extra_metadata`` (desired targets,
shift bounds, baseline feasibility) are **project design placeholders**
for demonstrating the engine end-to-end, not verified citations from a
literature review -- each entry's ``source`` field says so explicitly.
A future phase should replace these with vetted, cited values; nothing
here should be presented to a user as a scientifically validated
effect size. See ``docs/recommendation_engine.md`` "Candidate
intervention catalogue".
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Recommendation

_ASSUMPTION_DISCLAIMER = (
    "Synthetic project assumption for demonstration purposes only -- "
    "not a verified literature citation. See docs/recommendation_engine.md."
)

_REFERENCE_RECOMMENDATIONS: list[dict] = [
    {
        "intervention_code": "MORNING_LIGHT_EXPOSURE",
        "intervention_type": "light",
        "title": "Morning bright light exposure",
        "description": "Seek bright light shortly after waking.",
        "target_behavior": "morning_light_timing",
        "literature_expected_improvement_minutes": 15.0,
        "source": _ASSUMPTION_DISCLAIMER,
        "feasibility_notes": "Generally low-burden; commonly well-tolerated in the synthetic cohort.",
        "extra_metadata": {
            "contributor_signals": ["morning_light"],
            "value_kind": "duration_minutes",
            "direction": "increase",
            "template": "Try getting at least {target_value} of bright light within an hour of waking.",
            "desired_value_assumption": 30.0,
            "desired_value_relative_to": None,
            "max_shift_per_recommendation": 15.0,
            "min_target_value": 0.0,
            "max_target_value": 120.0,
            "baseline_feasibility": 0.65,
            "severity_applicability": [],
            "is_literature_verified": False,
        },
    },
    {
        "intervention_code": "EVENING_SCREEN_REDUCTION",
        "intervention_type": "screen",
        "title": "Reduce evening screen exposure",
        "description": "Reduce screen use in the hours before the target sleep time.",
        "target_behavior": "evening_screen_duration",
        "literature_expected_improvement_minutes": 15.0,
        "source": _ASSUMPTION_DISCLAIMER,
        "feasibility_notes": "Moderate burden; commonly the hardest habit to sustain in the synthetic cohort.",
        "extra_metadata": {
            "contributor_signals": ["evening_screen"],
            "value_kind": "clock_hour",
            "direction": "earlier",
            "template": "Try stopping screens by {target_time}.",
            "desired_value_assumption": -0.5,
            "desired_value_relative_to": "ideal_sleep_onset",
            "max_shift_per_recommendation": 1.5,
            "min_target_value": None,
            "max_target_value": None,
            "baseline_feasibility": 0.5,
            "severity_applicability": [],
            "is_literature_verified": False,
        },
    },
    {
        "intervention_code": "CONSISTENT_SLEEP_SCHEDULE",
        "intervention_type": "sleep",
        "title": "Consistent sleep/wake schedule",
        "description": (
            "Keep sleep onset and offset times consistent across the week, "
            "including free days."
        ),
        "target_behavior": "sleep_midpoint_variability",
        "literature_expected_improvement_minutes": 10.0,
        "source": _ASSUMPTION_DISCLAIMER,
        "feasibility_notes": "Harder on weekends/free days by definition of social jetlag.",
        "extra_metadata": {
            "contributor_signals": ["social_jetlag"],
            "value_kind": "duration_minutes",
            "direction": "decrease",
            "template": "Try keeping your free-day schedule within about {target_value} of your weekday schedule.",
            "desired_value_assumption": 0.0,
            "desired_value_relative_to": None,
            "max_shift_per_recommendation": 30.0,
            "min_target_value": 0.0,
            "max_target_value": None,
            "baseline_feasibility": 0.55,
            "severity_applicability": [],
            "is_literature_verified": False,
        },
    },
    {
        "intervention_code": "EARLIER_LAST_MEAL",
        "intervention_type": "meal",
        "title": "Earlier last meal",
        "description": "Move the last meal of the day earlier relative to sleep onset.",
        "target_behavior": "last_meal_time",
        "literature_expected_improvement_minutes": 8.0,
        "source": _ASSUMPTION_DISCLAIMER,
        "feasibility_notes": "Meal-timing shifts are typically easier than screen reduction in the synthetic cohort.",
        "extra_metadata": {
            "contributor_signals": ["meal_timing"],
            "value_kind": "clock_hour",
            "direction": "earlier",
            "template": "Try finishing your last meal by {target_time}.",
            "desired_value_assumption": -3.0,
            "desired_value_relative_to": "ideal_sleep_onset",
            "max_shift_per_recommendation": 1.0,
            "min_target_value": None,
            "max_target_value": None,
            "baseline_feasibility": 0.6,
            "severity_applicability": [],
            "is_literature_verified": False,
        },
    },
    {
        "intervention_code": "AFTERNOON_EXERCISE_TIMING",
        "intervention_type": "exercise",
        "title": "Adjust exercise timing",
        "description": (
            "Shift exercise timing away from the hours immediately before "
            "sleep onset."
        ),
        "target_behavior": "exercise_time",
        "literature_expected_improvement_minutes": 10.0,
        "source": _ASSUMPTION_DISCLAIMER,
        "feasibility_notes": "Depends heavily on the participant's schedule; kept conservative.",
        "extra_metadata": {
            "contributor_signals": ["exercise"],
            "value_kind": "clock_hour",
            "direction": "earlier",
            "template": "Try finishing exercise by {target_time}.",
            "desired_value_assumption": -4.0,
            "desired_value_relative_to": "ideal_sleep_onset",
            "max_shift_per_recommendation": 1.0,
            "min_target_value": None,
            "max_target_value": None,
            "baseline_feasibility": 0.6,
            "severity_applicability": [],
            "is_literature_verified": False,
        },
    },
    {
        "intervention_code": "REDUCE_LATE_CAFFEINE",
        "intervention_type": "caffeine",
        "title": "Reduce late-day caffeine",
        "description": "Move the last caffeine intake earlier in the day.",
        "target_behavior": "last_caffeine_time",
        "literature_expected_improvement_minutes": 5.0,
        "source": _ASSUMPTION_DISCLAIMER,
        "feasibility_notes": (
            "Not mapped to a Phase 9 ranked contributor signal (caffeine is not one of the "
            "five ranked signals) -- included in the catalogue for completeness but only ever "
            "selected via the engine's no-signal-match fallback path."
        ),
        "extra_metadata": {
            "contributor_signals": [],
            "value_kind": "clock_hour",
            "direction": "earlier",
            "template": "Try having your last caffeine by {target_time}.",
            "desired_value_assumption": -6.0,
            "desired_value_relative_to": "ideal_sleep_onset",
            "max_shift_per_recommendation": 1.5,
            "min_target_value": None,
            "max_target_value": None,
            "baseline_feasibility": 0.55,
            "severity_applicability": [],
            "is_literature_verified": False,
        },
    },
]


def seed_reference_data(session: Session) -> int:
    """Insert any reference recommendations that do not already exist.

    Returns the number of rows inserted.
    """

    existing_codes = set(
        session.execute(select(Recommendation.intervention_code)).scalars().all()
    )

    inserted = 0
    for entry in _REFERENCE_RECOMMENDATIONS:
        if entry["intervention_code"] in existing_codes:
            continue
        session.add(Recommendation(**entry))
        inserted += 1

    session.commit()
    return inserted

"""The candidate-intervention catalogue.

The catalogue itself lives in the database (``recommendations`` table,
seeded by ``app.database.seed``) -- this module never hard-codes which
interventions exist. It only defines the **structured shape** a
catalogue row's ``extra_metadata`` JSON blob is expected to carry, and
parses a raw ``Recommendation`` ORM row (or an equivalent plain dict,
for tests) into that shape.

Every numeric assumption embedded in ``extra_metadata`` (desired
targets, shift bounds, baseline feasibility) is a **project design
default**, explicitly labeled ``is_literature_verified=False`` unless
a real citation backs it -- see ``docs/recommendation_engine.md``
"Candidate intervention catalogue" for the full disclosure. This
phase does not fabricate a verified effect size for any intervention.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

# --- Value kinds (how a target is represented / interpolated) ---
CLOCK_HOUR = "clock_hour"          # a point on the 24h circle -- circular interpolation
DURATION_MINUTES = "duration_minutes"  # a plain magnitude -- linear interpolation
DURATION_HOURS = "duration_hours"

# --- Directions (what "improvement" means for this intervention) ---
EARLIER = "earlier"
LATER = "later"
INCREASE = "increase"
DECREASE = "decrease"

_DECREASING_DIRECTIONS = (EARLIER, DECREASE)
_INCREASING_DIRECTIONS = (LATER, INCREASE)


@dataclass(frozen=True)
class CandidateIntervention:
    """One catalogue row, fully parsed into the shape the engine needs."""

    intervention_id: int
    intervention_code: str
    intervention_type: str
    title: str
    is_active: bool

    contributor_signals: tuple  # Phase 9 signal names this intervention addresses (may be empty)
    value_kind: str  # CLOCK_HOUR | DURATION_MINUTES | DURATION_HOURS
    direction: str  # EARLIER | LATER | INCREASE | DECREASE

    template: str

    desired_value_assumption: float
    # If set, ``desired_value_assumption`` is an *offset* (hours) from
    # this anchor rather than an absolute value -- currently only
    # "ideal_sleep_onset" is supported.
    desired_value_relative_to: Optional[str]

    max_shift_per_recommendation: float  # same unit as value_kind
    min_target_value: Optional[float]
    max_target_value: Optional[float]

    baseline_feasibility: float
    severity_applicability: tuple  # subset of {"good","mild","moderate","severe"}; empty = all

    literature_expected_improvement_minutes: Optional[float]
    is_literature_verified: bool
    source_note: Optional[str]


def _get(metadata: dict, key: str, default):
    if not metadata:
        return default
    value = metadata.get(key, default)
    return default if value is None else value


def intervention_from_recommendation(recommendation, metadata: Optional[dict] = None) -> CandidateIntervention:
    """Parse a ``Recommendation`` ORM row (or a plain namespace/dict with
    the same attributes, for tests/fixtures) into a
    :class:`CandidateIntervention`.

    ``metadata`` overrides ``recommendation.extra_metadata`` when given
    (test convenience); normally the catalogue row's own JSON blob is
    used.
    """

    meta = metadata if metadata is not None else (getattr(recommendation, "extra_metadata", None) or {})

    signals = tuple(_get(meta, "contributor_signals", []))

    return CandidateIntervention(
        intervention_id=recommendation.id,
        intervention_code=recommendation.intervention_code,
        intervention_type=recommendation.intervention_type,
        title=recommendation.title,
        is_active=bool(getattr(recommendation, "is_active", True)),
        contributor_signals=signals,
        value_kind=_get(meta, "value_kind", DURATION_MINUTES),
        direction=_get(meta, "direction", DECREASE),
        template=_get(meta, "template", recommendation.description or "{title}"),
        desired_value_assumption=float(_get(meta, "desired_value_assumption", 0.0)),
        desired_value_relative_to=_get(meta, "desired_value_relative_to", None),
        max_shift_per_recommendation=float(_get(meta, "max_shift_per_recommendation", 60.0)),
        min_target_value=_get(meta, "min_target_value", None),
        max_target_value=_get(meta, "max_target_value", None),
        baseline_feasibility=float(_get(meta, "baseline_feasibility", 0.6)),
        severity_applicability=tuple(_get(meta, "severity_applicability", [])),
        literature_expected_improvement_minutes=getattr(
            recommendation, "literature_expected_improvement_minutes", None
        ),
        is_literature_verified=bool(_get(meta, "is_literature_verified", False)),
        source_note=getattr(recommendation, "source", None),
    )


def applies_to_severity(candidate: CandidateIntervention, severity: str) -> bool:
    """Empty ``severity_applicability`` means "applicable at every severity"."""

    return not candidate.severity_applicability or severity in candidate.severity_applicability


def direction_sign(direction: str) -> int:
    """``-1`` if the desired change moves the value earlier/down, ``+1`` if
    later/up. Used to detect and clamp a graduated-target computation
    that would (due to unusual input data) move the wrong way."""

    if direction in _DECREASING_DIRECTIONS:
        return -1
    if direction in _INCREASING_DIRECTIONS:
        return 1
    raise ValueError(f"Unknown intervention direction: {direction}")

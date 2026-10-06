"""Input and component-score data types for the alignment engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls
from typing import Optional


@dataclass(frozen=True)
class AlignmentInputs:
    """Everything :func:`app.alignment.engine.compute_alignment` needs.

    ``fused_dlmo_hour`` is the only DLMO-model-derived input -- this
    engine never touches XGBoost or the state engine directly, only
    the already-fused result (Phase 7's output).

    Two distinct time horizons are represented explicitly (see
    ``docs/alignment_engine.md`` "Time horizons"):

    - ``most_recent_sleep_onset_hour`` is the single most recently
      completed sleep period, used only for phase alignment.
    - The ``window_*`` sequences are the six most recent days
      (oldest to newest, matching Phase 4's window convention), used
      only for behavioral alignment -- so one anomalous night cannot
      by itself swing the behavioral score.

    Every ``window_*`` sequence should be exactly six entries long,
    with ``None`` for any day a signal was not observed;
    ``window_social_jetlag_minutes`` is expected to be ``None`` on
    non-free days by construction (Phase 3/4 only populate social
    jetlag for free days).
    """

    fused_dlmo_hour: float

    most_recent_sleep_onset_hour: Optional[float]

    window_sleep_onset_hours: list = field(default_factory=list)
    window_morning_light_duration_minutes: list = field(default_factory=list)
    window_evening_screen_duration_hours: list = field(default_factory=list)
    window_last_meal_hours: list = field(default_factory=list)
    window_social_jetlag_minutes: list = field(default_factory=list)

    chronotype: Optional[str] = None


@dataclass(frozen=True)
class ComponentScore:
    """The standard result shape for every scoring component (phase and
    behavioral alike) -- score plus enough context for a future UI/
    contributor-ranking phase to explain it, without this phase doing
    any natural-language generation itself.
    """

    name: str
    score: float  # 0-100
    raw_value: Optional[float] = None
    target: Optional[float] = None
    deviation: Optional[float] = None
    available: bool = True
    imputed: bool = False
    notes: str = ""

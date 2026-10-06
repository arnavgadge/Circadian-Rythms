"""Layer 3 of the Q26 fusion model: the biological continuity constraint.

Limits how far the proposed fused DLMO may move from the previous
fused DLMO in one day, using the shortest **signed circular**
difference -- never an ordinary numeric hour comparison, which would
be wrong across midnight (see the worked examples in
``docs/dlmo_fusion.md``).

This is fusion's own continuity rule, anchored on the previous *fused*
DLMO. It is deliberately independent of the Phase 6 state engine's
``adapted``/``current`` bounds around intrinsic DLMO -- those already
exist one layer down and are not re-implemented or re-checked here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.synthetic.time_utils import circular_diff_hours, normalize_hour


@dataclass(frozen=True)
class ContinuityResult:
    final_hour: float
    applied: bool
    adjustment_minutes: float  # how much the cap changed the proposed value (0 if not applied)
    raw_delta_minutes: float  # the proposed move before capping, signed


def apply_continuity_cap(proposed_hour: float, previous_hour: float, cap_minutes: float) -> ContinuityResult:
    """Cap the day-over-day move from ``previous_hour`` to ``proposed_hour``.

    If the shortest signed circular difference exceeds ``cap_minutes``
    in either direction, the result moves only ``cap_minutes`` in that
    same direction from ``previous_hour``; otherwise the proposal is
    returned unchanged.
    """

    raw_delta_hours = circular_diff_hours(proposed_hour, previous_hour)
    raw_delta_minutes = raw_delta_hours * 60.0
    cap_hours = cap_minutes / 60.0

    if abs(raw_delta_hours) <= cap_hours:
        return ContinuityResult(
            final_hour=proposed_hour, applied=False, adjustment_minutes=0.0, raw_delta_minutes=raw_delta_minutes
        )

    capped_delta_hours = math.copysign(cap_hours, raw_delta_hours)
    final_hour = normalize_hour(previous_hour + capped_delta_hours)
    adjustment_minutes = raw_delta_minutes - (capped_delta_hours * 60.0)
    return ContinuityResult(
        final_hour=final_hour, applied=True, adjustment_minutes=adjustment_minutes, raw_delta_minutes=raw_delta_minutes
    )

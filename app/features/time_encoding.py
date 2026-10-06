"""ML-facing circular time encoding.

Phase 3 (``app.synthetic.time_utils``) deliberately stopped short of
implementing sin/cos encoding -- that was explicitly deferred to "a
later phase". This is that phase: every clock-time value that enters
the feature vector goes through :func:`clock_to_sincos` here, never
through a bare linear scalar (23.5 instead of the encoded pair), so a
value near midnight never looks numerically "far" from a value just
after midnight.

For a clock hour ``h`` in ``[0, 24)``:

    sin_val = sin(2*pi*h / 24)
    cos_val = cos(2*pi*h / 24)

Both components are needed to invert the encoding uniquely -- sin
alone (or cos alone) cannot distinguish, e.g., 06:00 from 18:00.
"""

from __future__ import annotations

import math
from datetime import time
from typing import Optional

from app.synthetic.time_utils import clock_time_to_hour, hour_to_clock_time, normalize_hour

TWO_PI = 2.0 * math.pi
HOURS_PER_DAY = 24.0


def clock_to_sincos(hour: float) -> tuple:
    """Encode a clock hour (``[0, 24)``, wraps if outside) as ``(sin, cos)``."""

    normalized = normalize_hour(hour)
    angle = TWO_PI * normalized / HOURS_PER_DAY
    return math.sin(angle), math.cos(angle)


def sincos_to_clock(sin_val: float, cos_val: float) -> float:
    """Decode a ``(sin, cos)`` pair back to a clock hour in ``[0, 24)``.

    Uses ``atan2`` so the correct quadrant (and therefore the correct
    hour) is recovered regardless of sign; does not require ``sin**2 +
    cos**2 == 1`` exactly (a model's raw output rarely lands exactly on
    the unit circle), since ``atan2`` only depends on the angle.
    """

    angle = math.atan2(sin_val, cos_val)
    if angle < 0:
        angle += TWO_PI
    return angle / TWO_PI * HOURS_PER_DAY


def time_to_sincos(value: Optional[time]) -> Optional[tuple]:
    """Convenience wrapper: :func:`clock_to_sincos` from a ``datetime.time``."""

    if value is None:
        return None
    return clock_to_sincos(clock_time_to_hour(value))


def sincos_to_time(sin_val: float, cos_val: float) -> time:
    """Convenience wrapper: :func:`sincos_to_clock` to a ``datetime.time``."""

    return hour_to_clock_time(sincos_to_clock(sin_val, cos_val))

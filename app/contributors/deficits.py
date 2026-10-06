"""Signal <-> Phase 8 alignment-component mapping and deficit calculation.

``deficit = 100 - component_score``. Four of the five contributor
signals map directly onto an existing Phase 8 behavioral-alignment
component; **exercise does not**, because Phase 8's five-component
score has no dedicated exercise component (only sleep consistency,
morning light, evening screen, meal timing, and social jetlag). This
module does not invent a sixth alignment component to fill that gap --
see ``app.contributors.scoring`` for how exercise's contributor score
is computed instead (phase-effect-only, never a fabricated deficit).
"""

from __future__ import annotations

from typing import Optional

from app.alignment.engine import AlignmentResult

# Signals with a real Phase 8 alignment component.
SIGNAL_TO_COMPONENT = {
    "evening_screen": "evening_screen",
    "morning_light": "morning_light",
    "meal_timing": "meal_timing",
    "social_jetlag": "social_jetlag",
}

# Exercise deliberately has no entry: it must never receive a fabricated
# alignment-component deficit (see module docstring).
SIGNALS_WITHOUT_COMPONENT = ("exercise",)


def compute_alignment_deficit(signal: str, alignment_result: AlignmentResult) -> Optional[float]:
    """The 0-100 deficit for ``signal``, or ``None`` if ``signal`` has no
    corresponding Phase 8 component (currently: exercise only) or the
    component itself was unavailable."""

    component_name = SIGNAL_TO_COMPONENT.get(signal)
    if component_name is None:
        return None

    component = alignment_result.behavioral_components.get(component_name)
    if component is None or not component.available:
        return None

    return 100.0 - component.score

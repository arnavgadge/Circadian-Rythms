"""Normalization of raw phase effects across the candidate signals.

``normalized_effect = 100 * |effect| / max(|effect| across all candidates)``
-- a transparent max-scaling, not a statistical (z-score) normalization,
chosen so the largest contributor always scores exactly 100 and the
rest scale proportionally beneath it. If every candidate's absolute
effect is (numerically) zero, every normalized effect is 0 rather than
raising a divide-by-zero error.
"""

from __future__ import annotations

from typing import Optional


def normalize_absolute_effects(
    absolute_effects: dict, zero_effect_epsilon: float = 1e-9
) -> dict:
    """``absolute_effects``: signal name -> non-negative magnitude (or
    ``None`` if unavailable for that signal). Returns signal name ->
    normalized 0-100 value (``None`` preserved for unavailable signals).
    """

    available = [v for v in absolute_effects.values() if v is not None]
    max_effect = max(available) if available else 0.0

    if max_effect <= zero_effect_epsilon:
        return {name: (0.0 if value is not None else None) for name, value in absolute_effects.items()}

    return {
        name: (100.0 * value / max_effect if value is not None else None)
        for name, value in absolute_effects.items()
    }

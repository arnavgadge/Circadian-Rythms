"""Shared scoring-curve primitives.

One function, reused by every deviation-based component (phase score,
sleep consistency, social jetlag) so the "shape" of how a deviation
maps to a score is defined in exactly one place. The exact decay
constant differs per use (see ``app.alignment.config``), but the curve
family is the same everywhere: smooth, monotonically decreasing in the
deviation's magnitude, and bounded to ``(0, 100]``.
"""

from __future__ import annotations

import math


def exponential_decay_score(deviation: float, decay_constant: float, max_score: float = 100.0) -> float:
    """``max_score * exp(-|deviation| / decay_constant)``.

    Monotonically decreasing in ``|deviation|``; equals ``max_score``
    exactly at zero deviation and approaches (but never reaches) zero
    as the deviation grows. ``decay_constant`` must be positive.
    """

    if decay_constant <= 0:
        raise ValueError(f"decay_constant must be positive, got {decay_constant}")
    return max_score * math.exp(-abs(deviation) / decay_constant)


def tier_score(tier: str, tier_scores: dict, default: float) -> float:
    """Look up a tier's configured score, falling back to ``default`` for
    an unrecognized tier label rather than raising -- classification
    tiers are open-ended strings shared with Phase 3/6, not a closed
    enum this module owns."""

    return tier_scores.get(tier, default)

"""Compliance probability: how likely this participant is to actually
follow this intervention type -- a separate dimension from biological
effectiveness (see ``docs/personalization_engine.md`` "Compliance
interaction"). An intervention can be high-effect-low-compliance or
low-effect-high-compliance; the personal ranking score (Phase 1)
multiplies both together rather than conflating them.
"""

from __future__ import annotations

from typing import Optional, Sequence


def estimate_compliance_probability(historical_compliance_degrees: Sequence) -> Optional[float]:
    """The simple, transparent estimate: the mean of past compliance
    degrees (each already 0-1, from Phase 12's compliance evaluator).
    ``None`` with no history at all -- never fabricated as 0 or 1."""

    present = [v for v in historical_compliance_degrees if v is not None]
    if not present:
        return None
    return sum(present) / len(present)

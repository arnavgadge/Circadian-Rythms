"""Confound detection (Phase 1/2): did a behavior *other* than the
targeted one also change substantially between the baseline and
intervention periods?

No causal adjustment is attempted -- this only sets a transparent
``confound_flag`` so an observed DLMO/alignment change is never
presented as solely attributable to the target intervention when
other major signals moved too (see
``docs/intervention_effectiveness.md`` "Confounding").
"""

from __future__ import annotations

from dataclasses import dataclass

from app.effectiveness.config import DEFAULT_EFFECTIVENESS_CONFIG, EffectivenessConfig


@dataclass(frozen=True)
class ConfoundReport:
    confound_flag: bool
    changed_signals: dict  # signal -> delta_minutes, for every signal that exceeded its threshold


def detect_confounds(
    target_signal: str, signal_deltas_minutes: dict, config: EffectivenessConfig = DEFAULT_EFFECTIVENESS_CONFIG
) -> ConfoundReport:
    changed = {}
    for signal, delta in signal_deltas_minutes.items():
        if signal == target_signal or delta is None:
            continue
        threshold = config.confound_thresholds.get(signal)
        if threshold is not None and abs(delta) >= threshold:
            changed[signal] = delta

    return ConfoundReport(confound_flag=bool(changed), changed_signals=changed)

"""The Phase 14 safety-layer diagnostic report builder.

**All distributions here are properties of the Phase 3 synthetic
generator (plus, for confidence, a synthetic score assigned only for
this diagnostic run)** -- never evidence about real participants or
real disease prevalence (see ``docs/safety_and_confidence.md``
"Limitations").
"""

from __future__ import annotations

from dataclasses import dataclass


def summarize_safety_diagnostics(rows: list) -> dict:
    """``rows``: list of dicts with keys ``confidence_score``,
    ``confidence_label``, ``prediction_available``, ``flags``
    (list of flag_type strings active that evaluation),
    ``severities`` (list), ``recommendation_suppressed``,
    ``chronotype``, ``personality_key``."""

    n = len(rows)
    confidence_scores = [r["confidence_score"] for r in rows if r["confidence_score"] is not None]
    tier_counts: dict = {}
    for r in rows:
        tier_counts[r["confidence_label"] or "none"] = tier_counts.get(r["confidence_label"] or "none", 0) + 1

    flag_type_counts: dict = {}
    flags_by_chronotype: dict = {}
    flags_by_personality: dict = {}
    high_count = 0
    moderate_count = 0
    suppression_count = 0

    for r in rows:
        for flag_type in r["flags"]:
            flag_type_counts[flag_type] = flag_type_counts.get(flag_type, 0) + 1
            flags_by_chronotype.setdefault(r.get("chronotype"), {})
            flags_by_chronotype[r.get("chronotype")][flag_type] = flags_by_chronotype[r.get("chronotype")].get(flag_type, 0) + 1
            flags_by_personality.setdefault(r.get("personality_key"), {})
            flags_by_personality[r.get("personality_key")][flag_type] = flags_by_personality[r.get("personality_key")].get(flag_type, 0) + 1
        if "HIGH" in r["severities"]:
            high_count += 1
        elif r["severities"]:
            moderate_count += 1
        if r["recommendation_suppressed"]:
            suppression_count += 1

    return {
        "n_evaluations": n,
        "mean_confidence": (sum(confidence_scores) / len(confidence_scores)) if confidence_scores else None,
        "predictions_by_confidence_tier": tier_counts,
        "flag_counts_by_type": flag_type_counts,
        "flags_by_chronotype": flags_by_chronotype,
        "flags_by_personality": flags_by_personality,
        "high_severity_evaluations": high_count,
        "moderate_severity_evaluations": moderate_count,
        "recommendation_suppression_rate": suppression_count / n if n else None,
    }

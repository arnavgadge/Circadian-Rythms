# CircadianIQ Safety + Confidence Layer (Phase 14)

## 1. Purpose

Sits above the completed inference pipeline (Phases 4-13) and decides
**whether/how** to show what those phases already computed -- it never
recomputes or modifies a DLMO prediction, an alignment score, or any
personalization state. Five responsibilities: confidence gating,
persistent unusual-pattern detection (screening, not diagnosis), safe
output formatting metadata, recommendation suppression when required,
and auditability of every safety decision.

```
prediction -> confidence gate -> pattern detection -> safety decision -> safe output contract
```

Entry point: `app.safety.engine.SafetyEngine.evaluate(session, participant_id, as_of_date, fusion_result, alignment_result, recommendation)`.

## 2. Confidence thresholds

**Reused, never recomputed**: `app.safety.confidence_gate` consumes
`app.fusion.fuse.FusionResult.final_confidence`/`confidence_label`
directly. Phase 7's `DEFAULT_FUSION_CONFIG.confidence_label_thresholds`
is already exactly `(80, 60, 40)` -- the locked bands this phase
requires:

| Confidence | Label | `display_precision` | `prediction_available` |
|---|---|---|---|
| >= 80 | HIGH | `NORMAL` | `True` |
| 60-80 | MODERATE | `NORMAL_WITH_QUALIFIER` | `True` |
| 40-60 | LOW | `APPROXIMATE` | `True` |
| < 40 | NO_PREDICTION | `NONE` | `False` |

## 3. Data-quality interaction

The Q25 no-prediction rules (all Tier-1 signals missing, < 50% window
completeness, confidence < 40) are enforced exactly once, inside
`app.fusion.fuse.fuse` (`FusionResult.prediction_made`). This layer
reads that outcome and never overrides it -- even an anomalously high
raw confidence number cannot leak a prediction through if
`prediction_made` is `False`. Tier 1/2/3 signal definitions are also
reused unchanged from `app.features.config.DEFAULT_FEATURE_CONFIG`
(`tier_1_signals`/`tier_2_signals`/`tier_3_signals`), never redefined.

**Data quality and safety are deliberately separate axes**: a
participant can have high confidence with an active safety flag, or
low confidence with none. Confidence gating and pattern detection never
read each other's state to make their own decision.

## 4. Unusual-pattern detection (Layer 2) -- screening, not diagnosis

Rolling `rolling_horizon_days = 14`-day horizon. **The goal is not
diagnosis** -- it is deciding whether a persistent pattern is unusual
enough that generic behavioral recommendations alone may not be the
right next step. Every detector operates only on days with
`prediction_available=True`; a day with no prediction is excluded from
evidence entirely, never treated as supporting (or refuting) a trend.
No flag is ever raised from fewer than `min_observations_for_flag = 10`
available observations.

## 5. The four safety flags

All four thresholds below are **project screening parameters**, not
diagnostic criteria, and are never paired with a named clinical
condition in any user-facing text.

| Flag | Rule | Severity | Message |
|---|---|---|---|
| `persistent_late_phase` | mean estimated DLMO later than ~2:00 AM, >= 10 obs | MODERATE | "Your estimated biological clock has been consistently late for several weeks. If this affects your daily functioning, speaking with a sleep specialist may be helpful." |
| `persistent_early_phase` | mean estimated DLMO earlier than ~7:30 PM, >= 10 obs | MODERATE | "Your estimated biological clock is consistently early. If early waking or evening sleepiness affects you, a sleep specialist can help." |
| `continuous_dlmo_drift` | \|circular trend\| > ~20 min/day, >= 10 obs | **HIGH** | "Your estimated biological clock appears to be drifting consistently. If this pattern continues, a sleep specialist can help evaluate it." |
| `low_alignment_despite_compliance` | mean alignment < 45 AND mean compliance > 0.70, >= 10 obs each | MODERATE | "You've been following your recommendations consistently, but your alignment score remains low. This pattern may benefit from professional evaluation." |

## 6. Observation requirements

Every detector (`app.safety.patterns`) requires `min_observations_for_flag`
(10) **available** observations before it can trigger at all -- one or
two noisy estimates never raise a flag. "Available" means
`prediction_available=True` *and* the relevant value (DLMO, alignment,
compliance) is present; days with no prediction are simply absent from
the evidence set, not zero-filled or otherwise fabricated.

## 7. Circular trend handling

`app.safety.circular_stats.compute_circular_trend_minutes_per_day`:
unwraps the DLMO series (accumulating the shortest circular step
between consecutive observations -- 23:50 -> 00:05 -> 00:20 becomes a
smoothly increasing `[23.83, 24.08, 24.33]`, never a discontinuous
jump back near zero), then fits an ordinary-least-squares slope against
**calendar-day offset from the first observation** (so a gap in the
data does not compress the fitted trend into too few elapsed days).
`app.safety.circular_stats.signed_offset_from_midnight` similarly maps
the realistic DLMO arc (evening through early morning) onto a
monotonic signed scale with its one discontinuity placed at noon --
far from any plausible DLMO value -- so "later than 2:00 AM" /
"earlier than 7:30 PM" can be compared as ordinary numbers without
wraparound ambiguity. Verified directly against a stable
midnight-oscillating trajectory (23:55/00:05 alternating) producing a
near-zero trend, not a false drift flag.

## 8. Severity

Locked to exactly two levels. `continuous_dlmo_drift` is the only
`HIGH`-severity flag type; every other flag type is `MODERATE`
(`app.safety.lifecycle.determine_severity`). Multiple simultaneous
flags are always all retained (`SafeOutput.active_safety_flags`); the
highest severity among them determines suppression behavior, and one
primary safety message is chosen for a compact display while every
flag remains available internally.

## 9. Recommendation suppression

- **HIGH** (drift): `recommendation_suppressed = True`,
  `recommendation_available = False`; the behavioral recommendation is
  replaced with: *"Given your recent pattern, consider speaking with a
  healthcare professional rather than continuing behavioral adjustments
  alone."* -- not a diagnosis.
- **MODERATE**: `recommendation_suppressed = False`; the normal
  recommendation remains available, alongside the flag's message and
  the fixed non-diagnostic statement.

Flag lifecycle: `DETECTED -> PERSISTING -> RESOLVED`
(`app.safety.lifecycle.reconcile_flag`). Resolution requires
`resolution_min_normal_observations` (7) consecutive *available*
non-triggering observations -- a single normal day never resolves an
open flag. Per `safety_flags`' own append-only contract, only
`last_observed_date` and (on resolution) `resolved_date`/`resolved_by`
are ever mutated on an existing row; severity, message, and the
triggering statistics recorded at creation are never silently changed.

## 10. Wellness boundary

Every prediction-capable output carries
`boundary_note = "Estimated from behavioral patterns. Not a clinical measurement."`
Onboarding can additionally show the full statement:
*"CircadianIQ estimates your circadian phase from behavioral patterns.
It is not a medical device, does not perform laboratory measurements,
and does not diagnose any condition."* Both live as fixed constants in
`app.safety.messages`, never duplicated inline elsewhere.

## 11. Prohibited claims

`app.safety.guardrails.scan_for_prohibited_language` scans assembled
output text against `PROHIBITED_PHRASES` -- specific multi-word phrases
("you have DSWPD," "your clinical DLMO is," "take melatonin at," etc.),
deliberately **not** bare single words like "diagnos," since this
layer's own legitimate disclaimer text necessarily contains the word
"diagnosis" in a negated sentence. Verified: every listed prohibited
phrase is detected when present, and the real `NON_DIAGNOSTIC_STATEMENT`
constant produces zero matches.

## 12. Intervention catalogue validation

`app.safety.catalogue_guard.validate_recommendation_safety` checks a
recommendation's `intervention_type` against
`approved_intervention_types` (`screen`, `light`, `meal`, `exercise`,
`caffeine`, `sleep`) and scans its text against
`PROHIBITED_RECOMMENDATION_TERMS` (melatonin, medication, dosage,
prescri-, diagnos-, treatment, therapy, "mg "). Any failure **blocks**
the recommendation outright -- it is never shown, never logged-and-passed-through.

## 13. Audit trail

Uses `safety_flags` (Phase 2) exclusively -- no parallel safety
database. Five columns added by migration `c3f7a08e21b4`:
`message_key`, `first_detected_date`, `last_observed_date`,
`triggering_statistics` (JSON), `detection_version`. `circadian_labels`
gained three read-convenience columns in the same migration:
`safe_output_status`, `recommendation_suppressed`, `safety_severity`
-- populated by the safety layer, never by any earlier phase, and
never used to alter `fused_dlmo_sin/cos/time` or any other prediction
field on that row.

## 14. Versioning

Every stored flag records `detection_version` = the
`SafetyConfig.safety_config_version` active when it was created. If
detection logic changes, bump the version -- historical flags keep
their original version, so a later analysis can distinguish which
rule generated which flag.

## 15. Limitations

- All four flag thresholds (2:00 AM, 7:30 PM, 20 min/day, alignment
  45, compliance 0.70) and the 10/14/7-observation parameters are
  **project screening parameters**, chosen for this system's own
  escalation logic -- not sourced from, or claimed equivalent to, any
  validated clinical diagnostic criterion.
- This layer never diagnoses a named sleep or circadian disorder; its
  messages explicitly avoid naming one, and a hard-coded guardrail
  scan blocks specific prohibited phrases defensively.
- Confidence gating is entirely derived from Phase 7's existing
  computation; this phase adds no new confidence model.
- Diagnostic distributions (flag counts, confidence tiers, suppression
  rates) reported by `python -m app.scripts.run_safety_diagnostics`
  are properties of the Phase 3 synthetic generator and this run's own
  synthetic confidence assignment (Phase 3 has no fusion step) --
  never evidence about real disease prevalence.

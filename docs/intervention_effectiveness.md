# CircadianIQ Intervention Feedback / Effectiveness System (Phase 12)

## 1. Purpose

Measures whether a recommended intervention (Phase 10) appears
**associated with** improved circadian alignment over time, through a
locked three-phase progression of increasingly rigorous (but still
non-causal for Phases 1-2) observational analysis. This phase does not
implement long-term personalization decisions (Phase 13) -- it only
produces the evidence that phase will consume.

## 2. Intervention lifecycle

A small, explicit, **derived** state machine
(`app.effectiveness.lifecycle`) -- never a stored column, since it is
always reconstructable from `intervention_log`:

```
RECOMMENDED -> ACTIVE -> OBSERVED -> EVALUATED
                     \-> INSUFFICIENT_DATA / WAITING_FOR_HISTORY
```

An **episode** (`app.effectiveness.windows.detect_episodes`) is a run
of consecutive `intervention_log` days with the same
`recommendation_id`; a date gap or a switch to a different
recommendation always starts a new episode, even for the same
intervention recommended again later.

## 3. Compliance measurement

`app.effectiveness.compliance` implements one shared, transparent
**directional-decay** computation, parameterized per intervention by
its own `value_kind`/`direction` metadata (reused from
`app.recommendations.catalogue`, never redefined) plus a
per-intervention-type decay constant:

```
shortfall = deviation_minutes   if direction wants "earlier"/"decrease" (compliant when actual <= target)
shortfall = -deviation_minutes  if direction wants "later"/"increase"  (compliant when actual >= target)

compliance_degree = 1.0                      if shortfall <= 0
compliance_degree = exp(-shortfall / decay)  otherwise
```

**Asymmetric, not a symmetric decay around the target**: being at or
past the target in the desired direction is always full compliance
regardless of margin; only falling short degrades the score. Clock-time
deviations use `circular_diff_hours` throughout -- 23:55 vs. a midnight
target is +5 minutes early (full compliance), never "23h55m off."
`compliance_binary = compliance_degree >= compliance_binary_threshold`
(default `0.65`, configurable).

Named per-signal wrappers (`evaluate_screen_cutoff_compliance`,
`evaluate_morning_light_compliance`, `evaluate_meal_timing_compliance`,
`evaluate_exercise_compliance`, `evaluate_caffeine_compliance`,
`evaluate_social_jetlag_compliance`) make the "one evaluator per
intervention type" contract explicit; `evaluate_compliance()`
dispatches by Phase 9 contributor-signal name (or `intervention_type`
for caffeine, which has no Phase 9 signal).

**Compliance is computed after the fact**: Phase 11 writes a
recommendation for day N *before* day N's behavior exists;
`app.effectiveness.backfill.backfill_compliance` is the later step
that fills in `intervention_log.compliance_degree` /
`compliance_binary` / `actual_value_*` once day N's own
`daily_observations` row exists.

## 4. Phase 1: compliance-adjusted observational analysis

**Labeled `observational`.** Compares a `baseline_window_days` (7)
period strictly before the intervention episode against the most
recent `intervention_window_days` (7) days of the episode:

- `baseline_dlmo` / `recent_dlmo`: circular mean of the fused DLMO
  over each period (`app.effectiveness.outcomes.period_mean_dlmo_hour`).
- `dlmo_change_minutes`: the **circular** signed difference
  (`circular_diff_hours(recent, baseline) * 60`) -- never a naive
  subtraction.
- `baseline_alignment` / `recent_alignment` / `alignment_change`:
  plain means and difference (alignment scores are not circular).
- `compliance_rate = compliant_days / observed_days`, where
  `observed_days` counts only days compliance was actually computed
  (a missing observation is excluded, never counted as
  non-compliant).

A period with fewer than `min_window_completeness` (50%) of its
requested days observed returns `insufficient_baseline_history` or
`insufficient_intervention_history` rather than a computed value.

## 5. Phase 2: matched-period observational comparison

**Labeled `matched_observational`.** Enabled once at least
`min_history_days_for_phase2` (~4 weeks) of history exists. Finds the
**within-person** (never cross-participant) prior period most similar
to the intervention period on every *non-target* behavioral signal,
explicitly excluding the target signal from matching --
`app.effectiveness.phase2.find_matched_period` computes a transparent
standardized (z-scored by that signal's own historical circular/linear
standard deviation) mean distance across the matched variables for
every candidate period, and picks the minimum. A period is only used
if `similarity_score <= max_match_distance` (`match_valid`) and its
own data completeness clears `min_match_data_completeness`. Reports
`mean_dlmo_difference`, `slope_difference` (via a hand-rolled OLS
slope on a **circularly-unwrapped** DLMO series -- see
`app.effectiveness.phase2._unwrap_circular_series`), and
`mean_alignment_difference`.

## 6. Phase 3: longitudinal regression-controlled estimation

**Labeled `regression_controlled_estimate`.** A simple, interpretable
`sklearn.linear_model.LinearRegression` predicting daily DLMO change
(circular, minutes) from `compliance_degree` plus three behavioral
covariates (`morning_light`, `meal_timing`, `exercise` actual values)
and the previous day's DLMO deviation from the participant's own
baseline reference. The **compliance coefficient** is the personal
effect estimate, `effect_mins_per_compliance_unit`. Standard errors and
a `confidence_level`-based confidence interval are computed via the
standard OLS sampling-covariance formula (`MSE * (XᵀX)⁻¹`) since
scikit-learn's regressor does not provide them. Requires at least
`min_regression_observations` (21) complete rows (any row with a
missing covariate is dropped, never imputed) -- otherwise returns
`insufficient_data` rather than a misleading fit.

## 7. Circular DLMO handling

One authoritative rule, applied everywhere in this phase: **every DLMO
comparison uses `circular_diff_hours`** (already used throughout
Phases 3/6/7/8/9). 23:55 -> 00:10 is +15 minutes, never -23h45m. Period
means use `circular_mean_hours`; trajectory slopes first unwrap the
circular series (accumulating the shortest-arc step between
consecutive days) before fitting an ordinary linear slope, so a slope
crossing midnight is never computed as a huge discontinuous jump.

## 8. Confounding

`app.effectiveness.confound.detect_confounds` computes the
baseline-vs-intervention delta for every non-target signal
(`app.effectiveness.outcomes.compute_all_signal_deltas`, circular-aware
per signal) and flags `confound_flag = True` if any exceeds its own
configured threshold (`EffectivenessConfig.confound_thresholds`). No
causal adjustment is attempted -- this is a transparent disclosure
flag only, surfaced to the user as an explicit caveat (section 12).

## 9. Missing data

A missing observation is **not** non-compliance: `compliance_binary`
is `None` (unknown), not `False` (observed and non-compliant), for a
day with no resolvable actual value (e.g., `social_jetlag` is only
observable on free days by construction). Compliance rate, period
means, and regression rows all exclude missing days rather than
treating them as failures or fabricating a value.

## 10. Phase-transition rules

`app.effectiveness.dispatcher.evaluate_intervention_effect` always
evaluates Phase 1 first; if insufficient, returns `chosen_phase=None`
immediately (no Phase 2/3 attempt). Otherwise it independently checks
Phase 2's and Phase 3's own sufficiency gates and reports the
**highest** phase that actually cleared its gate -- Phase 3 is never
reported just because Phase 2 succeeded, and vice versa; each phase's
own minimum-sample/match-quality requirement is authoritative for
itself.

## 11. Stored estimates

`intervention_effect_estimates` (new table, additive-only migration --
`intervention_log` needed no schema change since
`compliance_binary`/`compliance_degree`/`actual_value_*`/
`target_value_*` already existed) stores one **immutable** row per
computed evaluation: `measurement_phase`, `interpretation`,
`effect_estimate`, confidence interval, `r_squared`,
`n_observations`, `compliance_rate`, `confound_flag`,
`methodology_version`, `model_version`, and a `diagnostics` JSON blob
with phase-specific detail (confound signals, match quality,
regression coefficients). A recomputation always **inserts a new
row** -- old estimates are never overwritten, keeping the full history
of how an estimate evolved auditable.

## 12. User-facing interpretation

`app.effectiveness.feedback.build_user_facing_feedback` assembles
**structured data only** (no natural-language generation) with a fixed
label keyed to the phase actually used:

| Phase | Label |
|---|---|
| 1 | "Observed change" |
| 2 | "Change compared with a similar previous period" |
| 3 | "Estimated personal effect" |

Never "This intervention caused X." When `confound_flag` is set, a
fixed caveat string is attached: *"Other behaviors also changed during
this period; the observed change may be shared across factors."*

## 13. Scientific limitations

- Phases 1-2 are **observational** -- association, not causation, even
  when a change lines up with an intervention's compliance.
- Phase 3 controls for a handful of measured covariates in one
  participant's own data; it cannot rule out unmeasured confounds or
  establish random-assignment-grade causal identification.
- All decay constants, window lengths, and thresholds are documented
  **project design choices**, not clinically validated parameters.
- Clock-hour regression covariates (Phase 3) are used as plain floats,
  valid in practice only because these signals cluster away from the
  midnight wrap point (the same convention Phase 8's meal-timing
  component already documents).
- Multiple simultaneous interventions (Phase 10 gives up to 3) are
  tracked with fully separate `recommendation_id` identities and never
  pooled into one coefficient; an observed change during an episode
  with another concurrently-changing signal is flagged via
  `confound_flag`, not silently attributed to one intervention.

## 14. Synthetic truth vs. estimated effects

Phase 3's synthetic generator produces **no** intervention/compliance
history automatically -- there is no "ground truth" intervention
effect anywhere in the core dataset. `python -m
app.scripts.run_effectiveness_diagnostics` is a **separate, explicitly
labeled controlled simulation harness** that injects known compliance
patterns and known true effects purely for testing whether Phase 12's
estimators recover a known answer; it does not modify or fabricate
anything in `app.synthetic`. A real participant never has a "true
effect" to compare against -- only the harness does. Diagnostic output
must never be read as evidence about real human intervention
effectiveness, only as a correctness check on the estimator.

## Worked examples

### Phase 1 -- screen intervention crossing midnight

Baseline week: fused DLMO clusters near 00:10 (`0.1667h`), alignment
score 61. Intervention week (evening-screen-reduction, 5/7 days
compliant): fused DLMO near 23:54 (`23.9h`), alignment score 74.

```
dlmo_change_minutes = circular_diff_hours(23.9, 0.1667) * 60 ≈ -16 min   (an advance, not "+23h44m")
alignment_change = 74 - 61 = +13
compliance_rate = 5/7 ≈ 0.71
```

User-facing: *"Observed change: Biological Clock 12:10 AM -> 11:54 PM
(~16 min advance). Score 61 -> 74."* If morning light also shifted by
more than its confound threshold that same week, the confound caveat
is attached.

### Phase 3 -- known synthetic ground truth recovery

The diagnostic harness injects a participant with an exact (noise-free)
rule: `daily_DLMO_change = -12.0 * compliance_degree`. Running the full
stack (`load_episodes` -> `load_intervention_records` ->
`evaluate_intervention_effect`) recovers
`effect_mins_per_compliance_unit ≈ -12.0` (mean absolute error on the
order of `1e-13` minutes in the noise-free case) -- confirming the
regression pipeline is wired correctly end-to-end, not a claim about
any real participant.

# CircadianIQ Alignment Engine (Phase 8)

## 1. Alignment objective

Converts the fused estimated DLMO (Phase 7's output) and the
participant's actual behavior into a personalized 0-100 alignment
score.

**A score of 100 means**: "your current routine is strongly aligned
with *your* estimated circadian phase." **It does not mean**: "your
routine matches a universal healthy bedtime." Two participants with
very different estimated phases (an early chronotype and a late one)
can both score 100 if each is well-aligned with their *own* estimate.

This phase only measures alignment. It does not rank contributors
(Phase 9), select interventions, or generate explanatory text.

## 2. The 60/40 architecture

```
final_alignment = 0.60 * phase_alignment + 0.40 * behavioral_alignment
```

Both components are 0-100. These weights are a **locked project design
choice** (`app.alignment.config.AlignmentConfig.phase_alignment_weight`
/ `behavioral_alignment_weight`), not a scientifically validated
universal ratio, and this phase does not change them.

## 3. Phase alignment

Compares the participant's actual sleep onset (the single most
recently completed night -- see section 10) against the **ideal sleep
onset** implied by the fused DLMO, using the shortest **circular**
signed difference (never a naive subtraction of raw clock hours).

### Ideal sleep timing derivation

```
ideal_sleep_onset = fused_DLMO + phase_to_sleep_offset   (default offset: +2.0 hours)
```

`app.alignment.ideal_sleep.derive_ideal_sleep_onset`, computed with
circular addition so it wraps correctly across midnight. **This +2
hour offset is a project modeling assumption** -- see section 14 --
not a claim of universally validated physiology. It is entirely
configurable (`AlignmentConfig.phase_to_sleep_offset_hours`).

An `app.alignment.ideal_sleep.derive_ideal_wake_time` helper is also
provided, deriving `ideal_sleep_onset + target_sleep_duration` **only**
when a reliable per-participant target sleep duration is supplied;
this phase does not invent a universal medical sleep-duration
recommendation to fill that gap when one isn't available, and simply
returns `None` in that case (the full ideal sleep *window* is left to
a later layer).

### Phase score curve

```
phase_score = 100 * exp(-|deviation_minutes| / phase_score_decay_minutes)   (default decay: 90 minutes)
```

A smooth, monotonically decreasing, bounded-`(0, 100]` curve --
`app.alignment.curves.exponential_decay_score`. The specific decay
constant is a Phase 8 design choice (calibration table below), **not**
claimed to be scientifically validated.

| Deviation | Score (decay=90 min) |
|---|---|
| 0 min | 100.0 |
| 15 min | 84.6 |
| 30 min | 71.7 |
| 60 min | 51.3 |
| 90 min | 36.8 |
| 120 min | 26.4 |
| 240 min | 7.0 |

### Worked examples (both verified by `tests/test_alignment_phase.py`)

**Example 1** -- DLMO = 23:45, ideal sleep onset = 01:45 (23:45 + 2h),
actual sleep onset = 02:00. Circular deviation = **+15 minutes** ->
phase score = **84.6** (high, as intended).

**Example 2** -- DLMO = 23:50, ideal sleep onset = 01:50, actual sleep
onset = 00:10. The actual sleep is **1h40 (100 minutes) earlier** than
ideal, not 22h20 later -- a naive subtraction of raw hours would
wrongly suggest the latter. Circular deviation = **-100 minutes** ->
phase score = 32.9.

## 4. Behavioral alignment: five components

```
behavioral_alignment =
      0.25 * sleep_consistency
    + 0.25 * morning_light
    + 0.20 * evening_screen
    + 0.15 * meal_timing
    + 0.15 * social_jetlag
```

Weights are locked (`AlignmentConfig`), validated to sum to exactly
1.0 at import time and again by `AlignmentConfig.validate()`
(`app.alignment.sanity` structurally re-checks this). **MEQ is not a
component and never influences behavioral alignment** -- it remains an
ML feature only (Phase 4), confirmed structurally by a dedicated test
that scans the alignment source for any MEQ reference.

All five components are computed over the **six-day window**, not a
single day (see section 10).

### Sleep consistency (25%)

Rewards *regularity*, not any particular clock time: the **circular
standard deviation** of the window's sleep-onset times
(`app.synthetic.time_utils.circular_std_hours`), passed through the
same exponential-decay curve family (default decay: 60 minutes). A
consistently-early and a consistently-late sleeper can both score near
100; a highly variable sleeper of either chronotype scores low. This
was deliberately designed and tested (`tests/test_alignment_behavioral.py::
test_sleep_consistency_does_not_reward_earliness_alone`) to satisfy the
brief's explicit "avoid giving a perfect score merely because sleep is
early" requirement.

### Morning light (25%) / Evening screen (20%) / Meal timing (15%)

Each classifies the window's mean value into the **same tiers already
established in Phase 3/6** (`app.state.behavioral_effect.
morning_light_tier` / `evening_screen_tier` / `last_meal_tier`, which
themselves reuse `app.synthetic.config.SyntheticAssumptions`
thresholds), then looks up a **Phase-8-specific score** for that tier:

| Morning light tier | none | short | moderate | high |
|---|---|---|---|---|
| Score | 25 | 55 | 85 | 100 |

| Evening screen tier | none | low | moderate | high | very_high |
|---|---|---|---|---|---|
| Score | 100 | 85 | 60 | 35 | 10 |

| Meal timing tier | before_8pm | 8-9pm | 9-10pm | 10-11pm | after_11pm |
|---|---|---|---|---|---|
| Score | 100 | 80 | 55 | 30 | 10 |

Reusing the tier *boundaries* (not redefining them) means alignment
can never silently disagree with the DLMO effect model about what
counts as, e.g., "heavy" screen use; only the *score* assigned to each
tier is new to this phase.

### Social jetlag (15%)

```
social_jetlag_score = 100 * exp(-jetlag_hours / social_jetlag_decay_hours)   (default decay: 1.5 hours)
```

A bounded, monotonically decreasing function -- **not** a linear `100 -
k * jetlag` deduction, which the brief explicitly warned against
(a linear deduction can cross zero or even go negative for large
enough jetlag; this curve never does). Jetlag is only ever recorded on
free days (Phase 3/4); a window with zero free days has no jetlag
observations at all, which is treated as a data-*availability* gap
(component unavailable, neutral fallback score), not evidence of zero
jetlag.

## 5. Component score contract

Every component (phase and behavioral alike) returns a
`ComponentScore`: `score` (0-100), `raw_value`, `target`, `deviation`,
`available`, `imputed`, and free-text `notes` -- enough structure for a
future UI or the Phase 9 contributor-ranking engine to explain *why* a
score is what it is, without this phase generating any natural-language
text itself.

## 6. Missing-data handling

Reuses the *concept* of Phase 4/7's tiered missing-data handling
without creating a second, competing confidence system:

- **Phase alignment**: if the current day's sleep onset is missing,
  falls back to the most recent available onset within the six-day
  window (marked `imputed=True`). If none exists anywhere, returns the
  configured `neutral_fallback_score` (50.0) with `available=False`.
- **Each behavioral component**: if it has zero usable observations
  anywhere in the window, returns the same neutral fallback with
  `available=False`; if some (but not all) window days are missing,
  it computes from what's available and marks `imputed=True`.

The top-level `AlignmentResult` exposes `data_completeness` (the
fraction of the 6 "slots" -- phase + 5 behavioral components -- that
were fully observed, not imputed) and `imputed_components` (which ones
weren't). Nothing is silently presented as directly observed when it
wasn't.

## 7. Time horizons -- explicit distinction

| Component | Time horizon |
|---|---|
| Phase alignment | The single most recently completed sleep period |
| All 5 behavioral components | The six most recent days (Phase 4's window convention) |

This is deliberate: phase alignment answers "how did last night
compare to your estimated ideal", while behavioral alignment answers
"how has your routine looked recently" -- a single anomalous night
should not by itself swing the behavioral score (verified by
`tests/test_alignment_engine.py::
test_behavioral_alignment_uses_window_not_single_anomalous_day`), and a
stale six-day average should not paper over what actually happened last
night for phase alignment (verified by `test_phase_alignment_uses_most_recent_day_not_window_average`).

## 8. Anti-circularity: why this phase may safely use sleep timing

Phase 4 deliberately excluded direct sleep timing (onset/offset/
midpoint) from the XGBoost DLMO predictor, specifically to prevent a
`sleep timing -> predicted DLMO -> ideal sleep timing -> alignment`
feedback loop that would make alignment trivially self-referential.
Because that exclusion holds, this phase can safely compare the
(sleep-timing-independent) fused DLMO against *actual* sleep timing
without reintroducing that loop. `app.alignment.sanity.
run_structural_checks` re-verifies, on every run, that:

- the Phase 4/5 feature manifest still excludes
  `sleep_onset`/`sleep_offset`/`sleep_midpoint_sin`/`sleep_midpoint_cos`
  (check 8), and
- the alignment engine itself never imports the trained XGBoost model
  or the state engine's transition logic -- only the already-fused
  DLMO value (check 7).

## 9. Output contract

```python
AlignmentResult:
    final_score, phase_score, behavioral_score            # all 0-100
    ideal_sleep_onset_hour, actual_sleep_onset_hour
    phase_difference_minutes
    behavioral_components: dict[str, ComponentScore]       # 5 entries
    data_completeness: float                               # 0-1
    imputed_components: list[str]
    diagnostics: dict
```

Fully serializable (plain dataclasses/dicts/floats/strings). Contains
enough structure for a future UI to render, e.g., "your sleep timing
is 15 minutes later than your estimated ideal" or "your behavioral
alignment is being reduced mainly by evening screen timing and social
jetlag" -- but generates no such text itself, and does not rank which
component matters most (that is Phase 9's job, using these same
component scores plus phase-shift effects and six-day history).

## 10. Database integration

Read-only (`app.alignment.db_adapter.build_alignment_inputs`), built
from `daily_observations` rows plus a fused DLMO value (e.g.
`circadian_labels.fused_dlmo_time`) -- mirroring the pattern already
established by `app.state.db_adapter`. No new table is created; the
existing `circadian_labels.final_alignment_score` /
`phase_alignment_score` / `behavioral_alignment_score` columns and the
`component_snapshot` JSON field (added in Phase 2 specifically for
"alignment component snapshots") are the intended eventual write
targets. This phase does not write to the database -- only a future
phase that owns the daily-inference write path does that.

## 11. Limitations

- **Every numeric parameter is a project design choice**: the 60/40
  split, the five behavioral weights, the +2 hour phase-to-sleep
  offset, every decay constant, and every tier-to-score mapping. None
  are presented as clinically validated.
- **Distributions on synthetic data reflect the synthetic generator's
  own assumptions**, not human circadian alignment (see the diagnostic
  report below). The correct reading is "under the current synthetic
  data-generating configuration, the alignment distribution is..." --
  never "X% of humans are aligned."
- **The neutral fallback score (50.0)** for fully-missing components is
  a placeholder, not a claim about what that participant's true
  alignment would have been.
- **No ideal sleep *window* (start and end)** is produced yet -- only
  the ideal onset, since no reliable per-participant target sleep
  duration exists in the current architecture; a later phase must
  supply one before a full window can be derived.

## Design assumptions vs. scientific claims

| Design assumption (this phase's choice) | Scientific claim (none made) |
|---|---|
| 60/40 phase/behavioral split | "Phase matters exactly 1.5x as much as behavior" |
| +2 hour sleep-onset-after-DLMO offset | "DLMO always precedes sleep onset by exactly 2 hours" (Phase 3 cites ~2h with noise as source-backed for a *different*, generation-time purpose; using a fixed +2h here for scoring is this phase's own simplification) |
| Exponential decay curves, all constants | Any specific decay rate as physiologically meaningful |
| Tier-to-score mappings | The DLMO-effect tier boundaries themselves are reused from Phase 3, but the *scores* assigned to them here are new and unvalidated |
| Neutral fallback = 50 | Any claim about what a participant's "true" score would be |

## Diagnostics (synthetic data)

`python -m app.scripts.run_alignment_diagnostics` -- run over 200
sampled participants (800 participant-windows), using the stored
`circadian_labels.fused_dlmo_time` (Phase 3's ground-truth trajectory)
directly as the fused DLMO input, a reasonable simplification for this
diagnostic (scoring alignment needs *a* fused value; it does not
require re-running the full Phase 5+6+7 pipeline for every window).

| Metric | Value |
|---|---|
| Rows | 800 |
| Final score | mean 55.1, std 17.0 |
| Phase score | mean 51.8 |
| Behavioral score | mean 60.0 |
| Mean data completeness | 1.000 (no missing values in the synthetic dataset) |

**By personality** (median final score, illustrative ranking observed):
`healthy_stable_routine` and `consistent_early_bird` scored highest;
`chaotic_sleeper`, `late_eater`, `screen_heavy_user`, and
`social_jetlag_student` scored lower -- consistent with, but not
independent confirmation of, how those personalities were *designed*
in Phase 3 (see the synthetic-data warning below).

**Important synthetic-data warning**: because the synthetic data
generator itself creates the behavioral patterns and DLMO relationships
these scores are computed from, this personality-ranking pattern
partly just reflects the simulator's own construction (e.g.
"screen-heavy" participants were built to use more evening screen, so
they score lower on evening screen -- by design, not discovery). **Do
not interpret this section as a clinical finding.** The correct
reading is "under the current synthetic data-generating configuration,
alignment differs across personalities in the expected direction" --
never "X% of humans in this category are misaligned."

## Module map

```
app/alignment/
    config.py                 AlignmentConfig: all weights/curves/thresholds, versioned (v1.0.0)
    inputs.py                  AlignmentInputs, ComponentScore
    curves.py                   exponential_decay_score, tier_score
    ideal_sleep.py               derive_ideal_sleep_onset, derive_ideal_wake_time
    phase_alignment.py            compute_phase_alignment
    behavioral_components.py       the 5 component scoring functions
    behavioral_alignment.py         compute_behavioral_alignment (weighted sum)
    engine.py                        compute_alignment() -- the single entry point
    sanity.py                        the 8 required sanity checks
    db_adapter.py                     read-side Phase 2 schema -> AlignmentInputs
    diagnostics.py                     synthetic-data distribution report

app/scripts/run_alignment_diagnostics.py   CLI entry point
```

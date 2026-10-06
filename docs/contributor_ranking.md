# CircadianIQ Contributor Ranking Engine (Phase 9)

## 1. Purpose

Answers one question: "of the behavioral signals CircadianIQ tracks,
which ones appear to be contributing most to this participant's
*current* misalignment?" It ranks; it does not diagnose, does not
select an intervention, and does not generate explanatory prose. It
also answers a second, deliberately **separate** question -- "is
today's behavior unusual compared to this person's own recent
history?" -- but that answer must never be confused with, or allowed
to change, the ranking (see section 12).

Everything downstream in this phase describes *modeled influence
within CircadianIQ's own architecture*, never a proven physiological
or medical cause. Result fields and any future explanatory text must
use "contributor" / "modeled influence" / "estimated phase effect" /
"alignment deficit" -- never "cause."

## 2. The five ranking signals

Exactly five candidates are ever ranked, always in this set
(`app.contributors.engine.SIGNALS`):

- `evening_screen`
- `morning_light`
- `meal_timing`
- `social_jetlag`
- `exercise`

Deliberately **excluded**: MEQ/chronotype questionnaire score,
intrinsic chronotype, DLMO itself, model confidence, and generic
"sleep quality" -- none of these are actionable behavioral levers in
the sense this engine ranks.

## 3. Contributor score formula (locked architecture)

For the three signals with both inputs available:

```
contributor_score = 0.60 * normalized_phase_effect + 0.40 * alignment_deficit
```

`phase_effect_weight` / `alignment_deficit_weight` in
`app.contributors.config.ContributorConfig` -- a **locked project
design choice**, not a scientifically validated universal ratio.

## 4. Phase-shift effect calculation

Reuses the exact same authoritative behavioral-effect model Phase 6
uses (`app.state.behavioral_effect.compute_behavioral_effect`) --
this phase never defines a second, potentially-contradictory effect
model. For each of the six window days, the shared model is called
once (`noise_minutes=0.0`, since ranking must be deterministic -- see
section 15) and the relevant per-signal component (light, screen,
meal, or exercise) is read off its breakdown and averaged across the
days that had complete data. A day missing any of its four required
raw values is **skipped**, never zero-filled.

Caffeine is not a ranked signal but is required by the shared model's
signature; a neutral placeholder (10:00, 0 mg -- inside that model's
own "no effect" zone) is supplied so it never contaminates the other
four signals' results.

## 5. Normalization

```
normalized_effect = 100 * |effect| / max(|effect| across all candidate signals)
```

Transparent max-scaling (not a z-score): the single largest
contributor in this window always normalizes to exactly 100, and the
rest scale proportionally beneath it. If every candidate's absolute
effect is numerically zero (`<= zero_effect_epsilon`), every
normalized effect is 0 rather than raising a divide-by-zero.

## 6. Alignment-component deficit calculation

```
alignment_deficit = 100 - alignment_component_score
```

`alignment_component_score` is read directly from Phase 8's
`AlignmentResult.behavioral_components` -- never recomputed here.

## 7. Signal <-> component mapping

| Signal            | Phase 8 component  |
|-------------------|---------------------|
| `evening_screen`  | `evening_screen`    |
| `morning_light`   | `morning_light`     |
| `meal_timing`      | `meal_timing`       |
| `social_jetlag`   | `social_jetlag`     |
| `exercise`        | *(none)*             |

## 8. Exercise and social jetlag: mirror-image asymmetry

Two signals are missing one of the two composite inputs, **by
construction**, and each falls back to its one available input rather
than a fabricated value for the other:

- **`exercise`** has a Phase 6 phase-shift effect but Phase 8's
  five-component behavioral score has no dedicated exercise component
  -> `contributor_score = 1.00 * normalized_phase_effect`
  (`weight_used = "phase_effect_only"`). It never receives a
  fabricated `alignment_deficit` or `alignment_component_score`
  (both are always `None` for this signal -- enforced by a dedicated
  sanity check and test).
- **`social_jetlag`** has a Phase 8 alignment component but no
  established direct DLMO-shifting formula in Phase 3/6 (jetlag is
  modeled there as a consistency/consequence measure, not an input
  like light/screen/meal/exercise) ->
  `contributor_score = 1.00 * alignment_deficit`
  (`weight_used = "deficit_only"`). It never receives a fabricated
  `signed_phase_effect_minutes` (`direction` classification handles
  this explicitly -- section 9).

If a composite signal (screen/light/meal) is missing just one of its
two inputs for a given participant/window (e.g. no alignment score
available), the same single-input fallback applies rather than
treating the missing side as zero.

## 9. Direction classification

Interpreted **relative to the participant's current phase deviation**
(Phase 8's `phase_difference_minutes`: positive = currently too
delayed, needs an advance; negative = too advanced, needs a delay) --
never a blind "any negative effect is good" rule.

- **`hurting`**: the signal's effect pushes in the *same* direction as
  the existing deviation (making misalignment worse), or -- for a
  deficit-only signal with no signed effect (social jetlag) -- a
  significant deficit with nothing to compare direction against.
- **`opportunity_missed`**: the effect pushes in the *corrective*
  direction, but only weakly (`< weak_corrective_effect_minutes_threshold`).
- **`neutral`**: the contributor score is below the significance
  threshold, the participant is already close to aligned
  (`|phase_deviation| < phase_deviation_neutral_zone_minutes`), or the
  corrective effect is already meaningfully large (already doing its
  job).

## 10. Significance threshold

`contributor_score < significance_threshold` (default 20.0) forces
`direction = "neutral"` and `significant = False` regardless of rank
-- prevents a weak, mostly-noise signal from looking like a major
contributor merely because it happened to rank highest among five.

## 11. Six-day habit-level ranking

The ranking is computed entirely from the **six most recent window
days**, oldest to newest (Phase 4's convention). It never reads
"today's" (`latest_*`) values -- those exist solely for anomaly
detection (section 12).

## 12. Today's anomaly detection (a separate concept)

A **robust, median/MAD-based** "modified z-score"
(`0.6745 * deviation / MAD`, Iglewicz & Hoaglin's commonly-cited
default threshold of 3.5 -- a documented, configurable starting point,
**not** claimed validated specifically for circadian behavioral data)
compares today's value to the participant's own six-day baseline.
Clock-time signals (`meal_timing`, `exercise`) use a **circular**
center and circular deviations, so a value just after midnight is
never mistaken for a huge outlier against a baseline clustered just
before midnight (verified with an explicit 23:5x/00:0x wraparound
test). When the baseline's MAD is numerically zero (a perfectly
consistent history), the method falls back to a fixed
absolute-deviation threshold so a genuinely novel value is still
caught. Fewer than `min_history_days_for_anomaly` (default 3) usable
window days makes the anomaly check `available = False` rather than
guessing.

**This anomaly flag never alters `contributor_score`, `rank`, or
`direction`** -- verified by a dedicated test that holds the six-day
window fixed, varies only `latest_evening_screen_duration_hours` from
"normal" to "wildly anomalous," and confirms the resulting
`contributor_score` and `rank` are identical while only
`anomaly_details["evening_screen"].is_anomaly` changes.

## 13. Missing-data behavior

- A day missing any required raw value is skipped for phase-effect
  purposes (section 4), not zero-filled.
- `data_quality` per signal is `"observed"` (all window days used),
  `"imputed"` (some window days skipped/missing but at least one slot
  existed), or `"unavailable"` (no window slots at all / no
  alignment-deficit possible).
- Fewer than 3 valid signals never triggers fabricating a third or
  fourth entry; `contributors` is simply shorter (see
  `test_fewer_than_three_valid_signals_does_not_fabricate`).

## 14. Limitations

- All weights, thresholds, and the normalization method are locked
  **project design choices**, chosen for interpretability and
  determinism -- not independently validated against real circadian
  outcome data.
- The phase-effect model (Phase 6) and the alignment components
  (Phase 8) are themselves calibrated against the Phase 3 synthetic
  generator's own assumptions, not measured human physiology.
- Exercise's phase-effect-only and social jetlag's deficit-only
  scoring are asymmetric by construction (section 8); this is a
  documented data-availability gap, not evidence that one signal
  matters twice as much as the other.
- No causal claim is made anywhere in this phase's output.

## 15. Synthetic-data interpretation warning

Every diagnostic distribution produced by
`python -m app.scripts.run_contributor_diagnostics` (top-1 frequency
by signal, mean contributor score by signal, anomaly frequency, the
personality-key breakdown) is a property of how the Phase 3 synthetic
generator constructs its behavioral personalities -- e.g. a
`screen_heavy_user` persona is *defined* to have high evening-screen
duration, so of course `evening_screen` ranks #1 for that persona.
These numbers demonstrate the engine is wired correctly and behaves
sensibly on data with known ground truth. They are **not** evidence
about the prevalence of any contributor in real human populations.

## Worked example

A participant currently 60 minutes too delayed
(`phase_difference_minutes = 60.0`), with:

- `evening_screen`: normalized effect 84.8 (heavy, delaying screen
  use), alignment component 30 (`deficit = 70`) ->
  `contributor_score = 0.60*84.8 + 0.40*70 = 78.9`, `direction =
  hurting` (a delaying effect aggravating an already-delayed
  participant).
- `social_jetlag`: alignment component 45 (`deficit = 55`) ->
  `contributor_score = 55.0` (deficit-only), `direction = hurting`
  (deficit-only signals can only ever be hurting or neutral).
- `morning_light`: light duration low (20 min), normalized effect
  42.4, alignment component 30 (`deficit = 70`) but the light effect
  is *corrective* (advancing) and small ->
  `contributor_score = 0.60*42.4 + 0.40*70 = 53.4`, `direction =
  opportunity_missed` (a chance to help that isn't being used to its
  potential).
- `exercise`: normalized effect 3.3 (near-negligible this window) ->
  `contributor_score = 3.3` (phase-effect-only), below the
  significance threshold -> `direction = neutral`.

Resulting top 3: `[evening_screen (78.9), social_jetlag (55.0),
morning_light (53.4)]`. This example is illustrative, built from
`app.contributors` fixtures directly, not asserted against the
synthetic generator's actual distribution (see section 15).

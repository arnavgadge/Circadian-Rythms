# CircadianIQ Feature Engineering (Phase 4)

## 1. Purpose

This phase transforms exactly six previous complete days of a
participant's raw behavioral history (Phase 2 schema, Phase 3
synthetic data) into the 68-feature Version-1 vector used to predict
`current_DLMO` on the next day. It produces **raw data -> 6-day window
-> feature engine -> 68-feature vector**, and stops there -- no
training, no evaluation, no fusion, no alignment.

The manifest below is generated directly from
[`app/features/feature_manifest.py`](../app/features/feature_manifest.py)
(`MANIFEST`), which is the actual, authoritative, machine-readable
list the builder iterates over. This document does not maintain an
independent copy of feature logic; it renders the same source of
truth the code runs against.

## 2. Feature architecture

```
daily_observations (SQL, Phase 2/3)
    |
app.features.windows            -- identify the 6-day window for a target date
    |
app.features.builder            -- per-day + per-window raw values
    |
app.features.aggregation        -- flat mean/std/ratio, recency-weighted mean
app.features.imputation         -- 3-tier missing-data fallback chain
app.features.time_encoding      -- sin/cos circular encoding
    |
68-feature vector (app.features.builder.FeatureVector)
    |
app.features.dataset            -- one row per (participant, window) -> X matrix
```

## 3. Feature groups

| Group | Count | Description |
|---|---|---|
| Raw daily circular signals | 48 | 4 non-sleep clock-time signals x 6 days x (sin, cos) |
| MSFsc | 2 | Window free-day sleep midpoint, circular |
| MEQ-derived | 2 | `meq_normalized`, `meq_msfsc_divergence` |
| Flat window aggregates | 10 | mean/std/ratio statistics over the 6-day window |
| Recency-weighted aggregates | 6 | recency-weighted counterpart of 6 of the above signals |
| **Total** | **68** | |

## 3.1 Complete feature manifest (68 rows, generated from app/features/feature_manifest.py)

| # | Feature | Source | Window | Aggregation | Encoding | Units | Tier | Purpose |
|---|---|---|---|---|---|---|---|---|
| 1 | `screen_end_day_1_sin` | evening_screen_end_time | day_1 | raw | sin | unitless (circular) | tier_1 | Evening screen end time -- source-backed phase-delay signal (Phase 3 config). |
| 2 | `screen_end_day_1_cos` | evening_screen_end_time | day_1 | raw | cos | unitless (circular) | tier_1 | Evening screen end time -- source-backed phase-delay signal (Phase 3 config). |
| 3 | `screen_end_day_2_sin` | evening_screen_end_time | day_2 | raw | sin | unitless (circular) | tier_1 | Evening screen end time -- source-backed phase-delay signal (Phase 3 config). |
| 4 | `screen_end_day_2_cos` | evening_screen_end_time | day_2 | raw | cos | unitless (circular) | tier_1 | Evening screen end time -- source-backed phase-delay signal (Phase 3 config). |
| 5 | `screen_end_day_3_sin` | evening_screen_end_time | day_3 | raw | sin | unitless (circular) | tier_1 | Evening screen end time -- source-backed phase-delay signal (Phase 3 config). |
| 6 | `screen_end_day_3_cos` | evening_screen_end_time | day_3 | raw | cos | unitless (circular) | tier_1 | Evening screen end time -- source-backed phase-delay signal (Phase 3 config). |
| 7 | `screen_end_day_4_sin` | evening_screen_end_time | day_4 | raw | sin | unitless (circular) | tier_1 | Evening screen end time -- source-backed phase-delay signal (Phase 3 config). |
| 8 | `screen_end_day_4_cos` | evening_screen_end_time | day_4 | raw | cos | unitless (circular) | tier_1 | Evening screen end time -- source-backed phase-delay signal (Phase 3 config). |
| 9 | `screen_end_day_5_sin` | evening_screen_end_time | day_5 | raw | sin | unitless (circular) | tier_1 | Evening screen end time -- source-backed phase-delay signal (Phase 3 config). |
| 10 | `screen_end_day_5_cos` | evening_screen_end_time | day_5 | raw | cos | unitless (circular) | tier_1 | Evening screen end time -- source-backed phase-delay signal (Phase 3 config). |
| 11 | `screen_end_day_6_sin` | evening_screen_end_time | day_6 | raw | sin | unitless (circular) | tier_1 | Evening screen end time -- source-backed phase-delay signal (Phase 3 config). |
| 12 | `screen_end_day_6_cos` | evening_screen_end_time | day_6 | raw | cos | unitless (circular) | tier_1 | Evening screen end time -- source-backed phase-delay signal (Phase 3 config). |
| 13 | `last_meal_day_1_sin` | last_meal_time | day_1 | raw | sin | unitless (circular) | tier_2 | Last meal time -- source-backed phase-delay signal (Phase 3 config). |
| 14 | `last_meal_day_1_cos` | last_meal_time | day_1 | raw | cos | unitless (circular) | tier_2 | Last meal time -- source-backed phase-delay signal (Phase 3 config). |
| 15 | `last_meal_day_2_sin` | last_meal_time | day_2 | raw | sin | unitless (circular) | tier_2 | Last meal time -- source-backed phase-delay signal (Phase 3 config). |
| 16 | `last_meal_day_2_cos` | last_meal_time | day_2 | raw | cos | unitless (circular) | tier_2 | Last meal time -- source-backed phase-delay signal (Phase 3 config). |
| 17 | `last_meal_day_3_sin` | last_meal_time | day_3 | raw | sin | unitless (circular) | tier_2 | Last meal time -- source-backed phase-delay signal (Phase 3 config). |
| 18 | `last_meal_day_3_cos` | last_meal_time | day_3 | raw | cos | unitless (circular) | tier_2 | Last meal time -- source-backed phase-delay signal (Phase 3 config). |
| 19 | `last_meal_day_4_sin` | last_meal_time | day_4 | raw | sin | unitless (circular) | tier_2 | Last meal time -- source-backed phase-delay signal (Phase 3 config). |
| 20 | `last_meal_day_4_cos` | last_meal_time | day_4 | raw | cos | unitless (circular) | tier_2 | Last meal time -- source-backed phase-delay signal (Phase 3 config). |
| 21 | `last_meal_day_5_sin` | last_meal_time | day_5 | raw | sin | unitless (circular) | tier_2 | Last meal time -- source-backed phase-delay signal (Phase 3 config). |
| 22 | `last_meal_day_5_cos` | last_meal_time | day_5 | raw | cos | unitless (circular) | tier_2 | Last meal time -- source-backed phase-delay signal (Phase 3 config). |
| 23 | `last_meal_day_6_sin` | last_meal_time | day_6 | raw | sin | unitless (circular) | tier_2 | Last meal time -- source-backed phase-delay signal (Phase 3 config). |
| 24 | `last_meal_day_6_cos` | last_meal_time | day_6 | raw | cos | unitless (circular) | tier_2 | Last meal time -- source-backed phase-delay signal (Phase 3 config). |
| 25 | `morning_light_start_day_1_sin` | morning_light_start_time | day_1 | raw | sin | unitless (circular) | tier_1 | Morning light start time -- source-backed phase-advance signal (Phase 3 config). |
| 26 | `morning_light_start_day_1_cos` | morning_light_start_time | day_1 | raw | cos | unitless (circular) | tier_1 | Morning light start time -- source-backed phase-advance signal (Phase 3 config). |
| 27 | `morning_light_start_day_2_sin` | morning_light_start_time | day_2 | raw | sin | unitless (circular) | tier_1 | Morning light start time -- source-backed phase-advance signal (Phase 3 config). |
| 28 | `morning_light_start_day_2_cos` | morning_light_start_time | day_2 | raw | cos | unitless (circular) | tier_1 | Morning light start time -- source-backed phase-advance signal (Phase 3 config). |
| 29 | `morning_light_start_day_3_sin` | morning_light_start_time | day_3 | raw | sin | unitless (circular) | tier_1 | Morning light start time -- source-backed phase-advance signal (Phase 3 config). |
| 30 | `morning_light_start_day_3_cos` | morning_light_start_time | day_3 | raw | cos | unitless (circular) | tier_1 | Morning light start time -- source-backed phase-advance signal (Phase 3 config). |
| 31 | `morning_light_start_day_4_sin` | morning_light_start_time | day_4 | raw | sin | unitless (circular) | tier_1 | Morning light start time -- source-backed phase-advance signal (Phase 3 config). |
| 32 | `morning_light_start_day_4_cos` | morning_light_start_time | day_4 | raw | cos | unitless (circular) | tier_1 | Morning light start time -- source-backed phase-advance signal (Phase 3 config). |
| 33 | `morning_light_start_day_5_sin` | morning_light_start_time | day_5 | raw | sin | unitless (circular) | tier_1 | Morning light start time -- source-backed phase-advance signal (Phase 3 config). |
| 34 | `morning_light_start_day_5_cos` | morning_light_start_time | day_5 | raw | cos | unitless (circular) | tier_1 | Morning light start time -- source-backed phase-advance signal (Phase 3 config). |
| 35 | `morning_light_start_day_6_sin` | morning_light_start_time | day_6 | raw | sin | unitless (circular) | tier_1 | Morning light start time -- source-backed phase-advance signal (Phase 3 config). |
| 36 | `morning_light_start_day_6_cos` | morning_light_start_time | day_6 | raw | cos | unitless (circular) | tier_1 | Morning light start time -- source-backed phase-advance signal (Phase 3 config). |
| 37 | `exercise_time_day_1_sin` | exercise_time | day_1 | raw | sin | unitless (circular) | tier_3 | Exercise timing -- illustrative phase-shift signal per the locked five-signal behavioral model. |
| 38 | `exercise_time_day_1_cos` | exercise_time | day_1 | raw | cos | unitless (circular) | tier_3 | Exercise timing -- illustrative phase-shift signal per the locked five-signal behavioral model. |
| 39 | `exercise_time_day_2_sin` | exercise_time | day_2 | raw | sin | unitless (circular) | tier_3 | Exercise timing -- illustrative phase-shift signal per the locked five-signal behavioral model. |
| 40 | `exercise_time_day_2_cos` | exercise_time | day_2 | raw | cos | unitless (circular) | tier_3 | Exercise timing -- illustrative phase-shift signal per the locked five-signal behavioral model. |
| 41 | `exercise_time_day_3_sin` | exercise_time | day_3 | raw | sin | unitless (circular) | tier_3 | Exercise timing -- illustrative phase-shift signal per the locked five-signal behavioral model. |
| 42 | `exercise_time_day_3_cos` | exercise_time | day_3 | raw | cos | unitless (circular) | tier_3 | Exercise timing -- illustrative phase-shift signal per the locked five-signal behavioral model. |
| 43 | `exercise_time_day_4_sin` | exercise_time | day_4 | raw | sin | unitless (circular) | tier_3 | Exercise timing -- illustrative phase-shift signal per the locked five-signal behavioral model. |
| 44 | `exercise_time_day_4_cos` | exercise_time | day_4 | raw | cos | unitless (circular) | tier_3 | Exercise timing -- illustrative phase-shift signal per the locked five-signal behavioral model. |
| 45 | `exercise_time_day_5_sin` | exercise_time | day_5 | raw | sin | unitless (circular) | tier_3 | Exercise timing -- illustrative phase-shift signal per the locked five-signal behavioral model. |
| 46 | `exercise_time_day_5_cos` | exercise_time | day_5 | raw | cos | unitless (circular) | tier_3 | Exercise timing -- illustrative phase-shift signal per the locked five-signal behavioral model. |
| 47 | `exercise_time_day_6_sin` | exercise_time | day_6 | raw | sin | unitless (circular) | tier_3 | Exercise timing -- illustrative phase-shift signal per the locked five-signal behavioral model. |
| 48 | `exercise_time_day_6_cos` | exercise_time | day_6 | raw | cos | unitless (circular) | tier_3 | Exercise timing -- illustrative phase-shift signal per the locked five-signal behavioral model. |
| 49 | `msfsc_sin` | free_day_sleep_midpoint_time (window free days only) | window | circular_mean | sin | unitless (circular) | tier_1 | Corrected free-day sleep midpoint (MSFsc) -- a chronotype-proxy phase estimate, NOT sleep onset. |
| 50 | `msfsc_cos` | free_day_sleep_midpoint_time (window free days only) | window | circular_mean | cos | unitless (circular) | tier_1 | Corrected free-day sleep midpoint (MSFsc) -- a chronotype-proxy phase estimate, NOT sleep onset. |
| 51 | `meq_normalized` | participant_profiles.meq_score | participant | derived | numeric | unitless [0, 1] | tier_2 | MEQ rescaled to [0, 1]: (MEQ - 16) / 70. Stable subjective chronotype predictor, not alignment input. |
| 52 | `meq_msfsc_divergence` | participant_profiles.meq_score, msfsc (window) | participant + window | derived | numeric | hours | tier_2 | Divergence between subjective chronotype (MEQ, mapped to an expected free-day phase) and actual behavioral free-day phase (window MSFsc). The MEQ->expected-phase mapping is an explicit modeling assumption (app.features.config), not a clinically validated formula. |
| 53 | `sleep_duration_mean_hours` | sleep_duration_minutes | window | mean | numeric | hours | tier_3 | Average nightly sleep duration over the window. |
| 54 | `sleep_duration_std_hours` | sleep_duration_minutes | window | std | numeric | hours | tier_3 | Night-to-night consistency of sleep duration. |
| 55 | `sleep_midpoint_variability_mean_minutes` | sleep_midpoint_variability_minutes | window | mean | numeric | minutes | tier_3 | Average day-to-day sleep-midpoint shift -- a consistency signal, not the midpoint itself. |
| 56 | `screen_duration_mean_hours` | evening_screen_duration_minutes | window | mean | numeric | hours | tier_1 | Average evening screen exposure duration. |
| 57 | `morning_light_duration_mean_minutes` | morning_light_duration_minutes | window | mean | numeric | minutes | tier_1 | Average morning light exposure duration. |
| 58 | `exercise_duration_mean_minutes` | exercise_duration_minutes | window | mean | numeric | minutes | tier_3 | Average exercise duration on days exercise occurred. |
| 59 | `exercise_frequency_ratio` | exercise_duration_minutes > 0 | window | ratio | numeric | unitless [0, 1] | tier_3 | Fraction of window days with any recorded exercise. |
| 60 | `caffeine_amount_mean_mg` | caffeine_amount_mg | window | mean | numeric | mg | tier_3 | Average daily caffeine amount. |
| 61 | `social_jetlag_mean_minutes` | social_jetlag_minutes (free days) | window | mean | numeric | minutes | tier_2 | Average social jetlag magnitude on the window's free days. |
| 62 | `free_day_ratio` | is_free_day | window | ratio | numeric | unitless [0, 1] | tier_1 | Fraction of window days that are free (non-work/school) days. |
| 63 | `sleep_duration_recency_weighted_hours` | sleep_duration_minutes | window | recency_weighted_mean | numeric | hours | tier_3 | Recency-weighted sleep duration (linear weights 1..6, oldest to newest). |
| 64 | `screen_duration_recency_weighted_hours` | evening_screen_duration_minutes | window | recency_weighted_mean | numeric | hours | tier_1 | Recency-weighted evening screen duration. |
| 65 | `morning_light_duration_recency_weighted_minutes` | morning_light_duration_minutes | window | recency_weighted_mean | numeric | minutes | tier_1 | Recency-weighted morning light duration. |
| 66 | `caffeine_amount_recency_weighted_mg` | caffeine_amount_mg | window | recency_weighted_mean | numeric | mg | tier_3 | Recency-weighted caffeine amount. |
| 67 | `social_jetlag_recency_weighted_minutes` | social_jetlag_minutes (free days) | window | recency_weighted_mean | numeric | minutes | tier_2 | Recency-weighted social jetlag magnitude. |
| 68 | `sleep_midpoint_variability_recency_weighted_minutes` | sleep_midpoint_variability_minutes | window | recency_weighted_mean | numeric | minutes | tier_3 | Recency-weighted sleep-midpoint variability. |

## 4. Sleep features deliberately removed

Direct sleep timing was removed from the Version-1 predictor
deliberately, everywhere in this manifest:

- No `sleep_onset_*` feature (sin, cos, or otherwise).
- No `sleep_offset_*` feature.
- No `sleep_midpoint_sin`/`sleep_midpoint_cos` feature.
- No weighted/recency-weighted sleep-onset feature.

**Why**: if sleep onset were a direct predictor input, the causal
chain becomes self-referential once a later phase compares actual
sleep timing against the predicted DLMO for alignment:

```
sleep onset -> predicted DLMO -> "ideal sleep onset" (DLMO + 2h) -> alignment vs. actual sleep onset
```

If sleep onset already predicted DLMO almost exactly, "alignment"
would trivially compare sleep onset against a linear transform of
itself. What **is** kept: sleep-*duration* (a magnitude, not a clock
position, so it carries no positional information about *when* sleep
happened), sleep-midpoint *variability* (a magnitude of day-to-day
change, not the midpoint itself), social jetlag, free-day ratio, and
MSFsc -- all of which describe behavioral consistency or a
free-day-specific chronotype proxy rather than directly encoding the
target's own timing.

The fourth raw daily clock-time signal (beyond screen/meal/light,
which the project brief names explicitly) is **exercise timing**, not
sleep onset -- chosen because, of the two remaining Phase 3 causal
signals (exercise, caffeine), exercise-timing phase-shift effects are
more established in general chronobiology than caffeine-timing
effects; caffeine *amount* is still captured, as a non-circular medium
aggregate. This is a feature-engineering design decision, not a
literature ranking -- see section 11.

## 5. Circular encoding, with midnight examples

Every clock-time feature is encoded as `(sin(2*pi*h/24),
cos(2*pi*h/24))`, never as a bare hour. Verified directly by
`tests/test_features_time_encoding.py`:

- `23:50` -> `(sin, cos) = (-0.0872, 0.9962)`
- `00:10` -> `(sin, cos) = (0.0436, 0.9990)`
- Euclidean distance between the two points: **0.086** -- a small
  angular step, correctly reflecting a **20-minute** true difference,
  not the ~23h40m a bare linear scalar would imply.
- `00:00`, `12:00`, `18:00`, `23:59` all round-trip through
  `clock_to_sincos` -> `sincos_to_clock` to within the encoding's
  second-level rounding.

## 6. Six-day window mapping

For target day `N`, the window is days `N-6 .. N-1` (`window.day_dates`,
oldest first), and `target_date == window_end + 1 day` always --
enforced by `Window.__post_init__` and re-checked by an explicit
assertion inside `build_features`:

```python
assert max(window.day_dates) == target_date - timedelta(days=1)
```

Example: target day 10 -> features use days 4, 5, 6, 7, 8, 9 (in that
order); day 10's own behavior never appears in its own feature vector.
`app.features.windows.compute_valid_windows` computes this from
whichever dates actually exist in the database (requiring `window_size
+ 1` strictly consecutive calendar days), so it is not hard-coded to
"days 1-30" -- it happens to produce exactly 24 windows per participant
for the Phase 3 30-day, gap-free dataset.

## 7. Recency weighting

One reusable utility, `app.features.aggregation.recency_weighted_mean`:
linear weights `(1, 2, 3, 4, 5, 6)` for day_1 (oldest) through day_6
(most recent), normalized to sum to 1 inside the function. Missing days
are dropped along with their weight and the rest renormalized, so a
window missing its oldest day still produces a sensible weighted mean
of what remains. This is an explicit, single, documented scheme -- not
several different ad hoc weightings, and not claimed to be a fitted or
biologically validated decay constant (see section 11).

## 8. Missing-data handling (Q25, feature-engineering half)

Three-tier fallback chain (`app.features.imputation`), applied
independently per feature:

1. **Window**: compute from the six days actually being used.
2. **Personal history**: the participant's own data strictly *before*
   `window_start` (never the window's target date or later).
3. **Population default**: a fixed, documented constant
   (`app.features.config.FeatureConfig`).

Every :class:`~app.features.builder.FeatureVector` carries
`missing_features`, `imputed_features`, `imputation_methods` (which of
the three tiers resolved each one), and `tier_missing_counts` --
nothing is silently filled in. `completeness = 1 - len(missing_features)
/ 68`. On the actual Phase 3 dataset (which has no missing values by
construction), every vector has `completeness == 1.0`; the fallback
chain is exercised and verified by
`tests/test_features_builder.py`'s deliberately-broken-data tests.

Signal tiers (as specified, extended where a feature doesn't map to
one of the nine named signals -- e.g. `sleep_duration`, `free_day_ratio`
-- with the extension documented per-feature in the manifest's `tier`
column):

- **Tier 1** (largest confidence penalty later): MSFsc/free-day sleep
  info, evening screen end, morning light.
- **Tier 2**: last meal, social jetlag, MEQ.
- **Tier 3**: exercise, caffeine, sleep-midpoint variability.

## 9. Leakage prevention

Enforced in three independent ways:

1. **Structural**: `build_features` computes `window_end = target_date
   - 1 day` and `window_start = target_date - 6 days` -- there is no
   code path that can read `target_date`'s own `daily_observations`
   row into the feature set.
2. **Assertion**: an explicit `assert max(window.day_dates) ==
   target_date - timedelta(days=1)` inside `build_features`, matching
   the brief's example.
3. **Validation checks**: `app.features.validation.validate_feature_vector`
   re-checks `target_date - window_end == 1 day` and `window_end -
   window_start == 5 days` as two of its 15 automated checks, on every
   generated vector.

The target itself (`circadian_labels.fused_dlmo_time` for
`target_date`) is read only as a *reference value* attached to the
returned `FeatureVector`/`FeatureDataset` for later phases to train
against -- it is never read back into `X`.

## 10. Temporal ordering

`day_dates[0]` (day_1) is always the oldest day, `day_dates[5]`
(day_6) the most recent completed day, enforced by `Window`'s
constructor validation (rejects any non-consecutive or misordered
date list). Feature names encode this explicitly (`screen_end_day_1_sin`
.. `screen_end_day_6_sin`), so the day index is never ambiguous or
silently reordered.

## 11. Assumptions

None of the following are claimed to be clinically or biologically
validated -- consistent with the Phase 3 rule that unsourced numbers
must be labeled as modeling assumptions, not presented as literature:

- **Recency weights** `(1, 2, 3, 4, 5, 6)`: a simple, explicit,
  configurable linear scheme. No fitted or published decay constant
  was available, so a plain linear scheme was chosen over inventing a
  more "sophisticated" one that would carry false precision.
- **MEQ -> expected free-day phase mapping** (for
  `meq_msfsc_divergence`): a linear interpolation between two
  illustrative anchor hours (`meq_morning_type_msfsc_hour=02:30` at
  MEQ=86, `meq_evening_type_msfsc_hour=06:30` at MEQ=16). This is
  exactly the "modeling assumption" the project brief calls out
  explicitly -- there is no cited MEQ-to-MSFsc regression backing
  these two numbers.
- **Population-default imputation constants**
  (`app.features.config.FeatureConfig`): fixed, round, documented
  values, not statistics fit from the generated dataset itself (fitting
  them from the data would make "population default" behavior depend
  on generation order, which is not a property a fallback constant
  should have).
- **Fourth raw daily signal = exercise timing, not caffeine timing**: a
  feature-engineering design choice (section 4), not a literature
  ranking.
- **`meq_msfsc_divergence` is not separately tracked as
  missing/imputed**: it is derived deterministically from
  `meq_normalized`'s and `msfsc`'s already-resolved (and separately
  tracked) values, so it never itself needs a fourth fallback path;
  if either input was imputed, that is visible via the two other
  features' own tier-missingness entries.
- **`free_day_ratio`/`exercise_frequency_ratio` denominators**: computed
  over whichever of the 6 window days actually have a non-null
  `is_free_day`/`exercise_duration_minutes` value; if a day's entire
  `daily_observations` row is absent, that day is excluded from the
  ratio's denominator rather than assumed one way or the other.

## 12. Where things live (module map)

```
app/features/
    config.py            recency weights, population defaults, MEQ->MSFsc mapping, tier lists
    time_encoding.py      clock_to_sincos() / sincos_to_clock() (+ datetime.time convenience wrappers)
    aggregation.py         flat_mean, flat_std, ratio, recency_weighted_mean
    windows.py             Window dataclass + compute_valid_windows()
    imputation.py           ImputationRecord + 3-tier fallback resolvers
    feature_manifest.py     the 68-entry authoritative FeatureSpec list (MANIFEST)
    builder.py              build_features(participant_id, target_date, session) -> FeatureVector
    dataset.py               build_feature_dataset(participant_ids, session) -> FeatureDataset
    validation.py            the 15 automated sanity checks
    diagnostics.py           per-feature statistics report (missingness, min/max/mean/std, near-constant)

app/scripts/build_feature_dataset.py   CLI entry point
```

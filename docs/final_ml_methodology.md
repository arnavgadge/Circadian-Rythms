# CircadianIQ Final ML Methodology (Phase 18 release consolidation)

**Release:** v1.0.0-research-demo. **Model version:** `v1.1` (XGBoost sin/cos twin-model, `models/xgboost_dlmo_sin_v1.pkl` / `models/xgboost_dlmo_cos_v1.pkl` / `models/model_metadata_v1.json`).

> **This model is trained and validated exclusively on SYNTHETIC data.**
> Its performance does **not** demonstrate equivalent performance on
> real human DLMO measurements. No component of CircadianIQ has ever
> been validated against a real human dim-light melatonin onset assay.
> Every performance figure in this document describes **93.73% of
> held-out synthetic test windows** falling within +-60 minutes -- never
> "93.73% accurate on humans" or any phrasing implying clinical or
> real-human validation. This qualifier applies to every number below,
> repeated explicitly rather than left implicit.

This document is the final, consolidated ML writeup, built from
Phase 5's original methodology (`docs/model_training_and_validation.md`,
preserved as the detailed phase record) plus the exact validated
result artifacts frozen for release under `release/results/*.csv` and
`release/figures/*.png`, cross-checked directly against
`models/model_metadata_v1.json` and the relevant source modules. No
number below was recomputed for this document; every number is read
from those existing sources.

## 1. Problem definition

Predict the target day's `current_DLMO` (a circadian phase marker,
represented as a clock time) from the six previously completed days of
a participant's behavior -- a 68-feature, six-day trailing-window
vector (Phase 4). This is regression over a **circular** target (a
clock time, where 23:59 and 00:01 are two minutes apart, not ~24
hours), solved as two independent regressions -- `sin(DLMO)` and
`cos(DLMO)` -- decoded back to a clock hour after prediction.

## 2. Data flow: synthetic observations -> six-day windows -> 68-feature vector -> circular target

1. **Synthetic observations** (Phase 3, `app/synthetic/`): a
   generative model produces daily behavioral records
   (`daily_observations` rows) for each synthetic participant, driven
   by a source-backed chronotype/DLMO distribution and seven synthetic
   behavioral personalities (see `docs/scientific_assumptions.md` for
   the full literature-backed vs. project-modeling-assumption
   breakdown of every constant used here).
2. **Six-day trailing windows** (Phase 4, `app.features.builder`): for
   a target date `N`, the feature window covers days `N-6 .. N-1` --
   the target day's own behavior is never included, enforced by a
   runtime assertion (`app/features/builder.py:177-181`,
   `max(day_dates) == target_date - 1`) that Phase 17's temporal-
   leakage audit exercised against real injected data, not just
   inspected as a code comment.
3. **68-feature representation** (`app.features.feature_manifest`):
   see section 3.
4. **Circular DLMO target** (`app.features.time_encoding.clock_to_sincos`,
   reused unmodified by the model-training phase): see section 5.

## 3. Feature representation -- exactly 68 features

`app.features.feature_manifest.MANIFEST` is the single source of
truth; `len(MANIFEST) == 68` is asserted at import time so a silent
count drift fails immediately. Groups, in manifest order:

1. **Raw daily circular signals (48)** -- four non-sleep clock-time
   signals x six window days x (sin, cos): evening screen end time,
   last meal time, morning light start time, and one more non-sleep
   signal per day, each sin/cos encoded rather than left as a bare
   scalar hour.
2. **MSFsc, circular (2)** -- corrected free-day sleep midpoint for
   the window, sin/cos encoded.
3. **MEQ-derived (2)** -- `MEQ_normalized`, `MEQ_MSFsc_divergence`.
4. **Flat window aggregates (10)** -- mean/std/ratio statistics over
   the six-day window.
5. **Recency-weighted aggregates (6)** -- the recency-weighted
   counterpart of six of the flat signals above.

`48 + 2 + 2 + 10 + 6 = 68`.

**Sleep onset/offset/midpoint timing is deliberately excluded from
every feature** -- including it would let the model trivially
reconstruct DLMO from sleep timing rather than learn the intended
behavior -> phase relationship. This exclusion is enforced twice: at
manifest-authoring time (no sleep-timing `FeatureSpec` exists) and at
runtime, where `app.features.validation.validate_feature_vector`
rejects a feature vector containing any forbidden sleep-onset/offset
pattern. Phase 17's feature-contract audit exercised this rejection
against a real, deliberately mutated `FeatureVector` (injecting a raw
`sleep_onset_hour_raw` feature, and separately a physiology feature)
and confirmed both were correctly rejected, with a negative control
confirming a genuine vector still passes.

### `feature_manifest_version` discrepancy (must be stated honestly, not silently resolved)

The frozen model artifact's own metadata
(`models/model_metadata_v1.json:"feature_manifest_version": "phase4-v1"`)
records the manifest tag active at training time as `"phase4-v1"`.
The current code constant
(`app/features/feature_manifest.py:FEATURE_MANIFEST_VERSION`) is
`"1.0.0"`. **This is a version-label naming inconsistency, not a
feature-set change** -- the underlying 68-feature manifest itself has
not changed since training (verified directly by Phase 17's audit 5,
which compared the manifest's own import-time assertion against
`build_features()`'s real output, exact order, not just set
equality). `release/version_manifest.json` records both values rather
than silently picking one, and this document does the same.

## 4. Train/test participant split (participant-level, not window-level)

`app.models.splitting.split_participants(participant_ids,
test_fraction, seed)` shuffles **participant IDs**, never rows, with a
seeded `numpy.random.default_rng`, then slices the boundary --
deterministic, so the same seed reproduces the same split every time,
and a participant can never land on both sides. This is the single
most important leakage guard in the ML phase.

Realized split (`release/results/test_summary.csv`,
`models/model_metadata_v1.json`):

| | Value |
|---|---|
| Split seed | 2025 |
| Split version | v1 |
| Test fraction | 0.2 |
| Train participants / windows | 800 / 19,200 |
| Test participants / windows | 200 / 4,800 |

`set(train_ids).isdisjoint(test_ids)` is asserted in code and by
dedicated tests. Phase 17's participant-leakage audit independently
re-derived the actual split and every GroupKFold fold directly from
`app.models.splitting`/`app.models.training` (not hardcoded lists)
against a real dataset and confirmed all disjoint; it also confirmed
no global `.fit()`/scaler/imputer exists anywhere in `app/features`
or `app/models` (XGBoost needs none, confirmed by grep and by the
codebase's own docstrings). The 200 held-out test participants are
read exactly once, at the final evaluation step -- never during
GroupKFold CV, never during hyperparameter selection (no
hyperparameter search was performed at all, per the project brief;
see section 6).

## 5. GroupKFold cross-validation methodology

Inside the 800 training participants only:
`sklearn.model_selection.GroupKFold(n_splits=5)`, grouped by
`participant_id`, so every window belonging to one participant lands
in exactly one fold. Ordinary row-based `KFold` is never used anywhere
in this codebase for model selection. Each fold: 640 training
participants (15,360 windows) / 160 validation participants (3,840
windows), confirmed programmatically per fold
(`app.models.training.run_grouped_cross_validation` asserts
`train_groups.isdisjoint(val_groups)`, re-checked by a dedicated
test).

## 6. XGBoost sin/cos twin-model approach

Two independent `xgboost.XGBRegressor` models -- one for `sin(DLMO)`,
one for `cos(DLMO)` (`app.models.xgboost_model.DualComponentXGBModel`).
Native multi-output support was verified to exist in the installed
`xgboost==3.4.1`, but was deliberately not used: per the project
brief's preference for "the simplest reliable implementation" over an
unverified-across-versions native path, and to keep feature
importance / SHAP analysis unambiguous per target component.

**Exact hyperparameters** (`app.models.config.XGBoostHyperparameters`,
confirmed identical in `models/model_metadata_v1.json`), the project's
own documented "engineering starting points," **not claimed optimal**:

```
n_estimators     = 500
max_depth        = 6
learning_rate    = 0.05
subsample        = 0.8
colsample_bytree = 0.8
random_state     = 42
objective        = reg:squarederror
```

No hyperparameter search was performed in this phase, per the brief.

## 7. Circular decoding

Encoding (`app.features.time_encoding.clock_to_sincos`, the same
utility used by the feature layer, not reimplemented here): for clock
hour `h` in `[0, 24)`, `sin_val = sin(2*pi*h/24)`,
`cos_val = cos(2*pi*h/24)`.

Decoding a **prediction** is not the same as decoding a true encoded
value: nothing constrains a model's raw `(sin, cos)` output to the
unit circle. `app.models.target_encoding.decode_predictions`
normalizes first:

```
r = sqrt(sin^2 + cos^2)
if r > 0: sin_norm, cos_norm = sin/r, cos/r
hour = atan2(sin_norm, cos_norm) -> [0, 24)
```

Verified against both an inflated (magnitude 2.5) and a shrunk
(magnitude 0.1) synthetic prediction vector, confirming the decoded
hour is unaffected by the raw output's magnitude.

Every evaluation metric in this document is a **circular error**
(`app.models.evaluation.circular_error_minutes`: `actual - predicted`,
shortest signed arc) -- 23:50 vs. 00:10 is a 20-minute error, never
the ~23h40m a naive linear subtraction would produce. All CV, test,
and stratified metrics below are computed on decoded clock hours,
never on raw sin/cos component error.

## 8. Baseline models

Neither baseline uses sleep-onset timing (that would violate the
anti-circularity design the feature layer itself enforces).

- **Baseline 1 -- participant mean**: predicts each test
  participant's circular mean *training-target* DLMO (from that
  participant's own training windows).
- **Baseline 2 -- MSFsc proxy**: decodes the already-computed
  `msfsc_sin`/`msfsc_cos` features directly as a naive DLMO guess,
  with no learned parameters -- MSFsc is the one phase-related signal
  the feature architecture explicitly sanctions as not being direct
  sleep-onset timing.

All rows computed on the identical 200-participant, 4,800-window
held-out test set (`release/results/baseline_comparison.csv`):

| Model | MAE (min) | RMSE (min) | Median abs. error (min) | % within +-60 min |
|---|---|---|---|---|
| **XGBoost (this model, v1.1)** | **24.47** | **31.86** | **19.71** | **93.73** |
| Baseline 1: participant mean | 57.23 | 75.16 | 43.47 | 67.56 |
| Baseline 2: MSFsc proxy | 342.10 | 349.90 | 333.03 | 0.0 |

XGBoost cuts the participant-mean baseline's error by more than half.
The MSFsc baseline's large, roughly constant offset is expected, not
a bug: MSFsc measures sleep *midpoint*, while DLMO is approximately
`sleep_onset - 2h`, a structural several-hour gap a non-learned
baseline cannot correct for.

## 9. Held-out test metrics

Computed **exactly once**, on the 200 held-out test participants
(4,800 windows), after final training on all 800 training
participants (`release/results/model_metrics.csv`,
`models/model_metadata_v1.json:"test_metrics"`):

| Metric | Value |
|---|---|
| n (windows) | 4,800 |
| MAE | 24.47 min |
| RMSE | 31.86 min |
| Median absolute error | 19.71 min |
| % within +-15 min | 39.56% |
| % within +-30 min | 69.40% |
| **% within +-60 min** | **93.73%** |
| % within +-90 min | 98.67% |
| Signed mean error (bias) | -0.82 min |
| Signed std of error | 31.85 min |
| p90 absolute error | 51.05 min |
| p95 absolute error | 64.99 min |

**93.73% of held-out synthetic test windows were within +-60 minutes.**
This is the headline result, and it describes synthetic-data
performance only.

## 10. 5-fold GroupKFold cross-validation metrics

(`release/results/cv_per_fold.csv`, `models/model_metadata_v1.json:"cv_metrics"`)

| Fold | Train participants | Val participants | MAE (min) | RMSE (min) | % within 60 min |
|---|---|---|---|---|---|
| 0 | 640 | 160 | 26.57 | 33.63 | 92.27 |
| 1 | 640 | 160 | 24.98 | 32.56 | 92.60 |
| 2 | 640 | 160 | 26.45 | 34.17 | 92.66 |
| 3 | 640 | 160 | 23.32 | 30.38 | 94.35 |
| 4 | 640 | 160 | 24.79 | 31.76 | 93.28 |
| **Mean +- std** | | | **25.22 +- 1.20** | **32.50 +- 1.35** | **93.03 +- 0.74** |

Low fold-to-fold variance (MAE std of 1.2 minutes on a ~25-minute
mean) indicates the baseline configuration is reasonably stable across
different training-participant subsets, on this synthetic dataset.

## 11. Chronotype-stratified results

(`release/results/chronotype_metrics.csv`; figure:
`release/figures/05_performance_by_chronotype.png`)

| Chronotype | n participants | n windows | MAE (min) | % within 60 | Bias (min) |
|---|---|---|---|---|---|
| Early | 55 | 1,320 | 29.99 | 89.47 | -11.33 |
| Intermediate | 119 | 2,856 | **20.04** | **97.79** | -0.27 |
| Late | 26 | 624 | 33.07 | 84.13 | +18.90 |

Intermediate chronotype (59% of the synthetic population, and the
chronotype with the smallest source-backed DLMO standard deviation,
12 minutes -- see `docs/synthetic_data_generation.md`) is predicted
noticeably better than Early or Late. Late chronotype has both the
worst MAE and the largest positive bias -- plausibly explained by Late
being both the smallest population share and the chronotype with the
largest source-backed DLMO spread. The model does **not** perform
equally across chronotypes; this should inform any later phase
consuming its predictions.

## 12. Personality-stratified results

(`release/results/personality_metrics.csv`; figure:
`release/figures/06_performance_by_personality.png`)

| Personality | n participants | n windows | MAE (min) | % within 60 | Bias (min) |
|---|---|---|---|---|---|
| Consistent early bird | 14 | 336 | 30.82 | 86.01 | +7.31 |
| Consistent night owl | 14 | 336 | 25.18 | 92.56 | -3.48 |
| Social jetlag student | 50 | 1,200 | 20.59 | 97.25 | -4.22 |
| Chaotic sleeper | 25 | 600 | 29.21 | 89.50 | +6.68 |
| Healthy stable routine | 28 | 672 | 28.95 | 90.18 | +1.21 |
| Screen-heavy user | 46 | 1,104 | 20.26 | 97.37 | -5.99 |
| Late eater | 23 | 552 | 26.41 | 93.12 | +2.94 |

The two most-represented personalities (screen-heavy user, 18% of the
synthetic population; social jetlag student, 25%) have the lowest MAE
-- consistent with those groups also having the most *training*
examples, not necessarily with their behavior being intrinsically
easier to predict. Consistent early bird (the smallest group, 8%) has
the highest MAE. This pattern -- performance tracking training-set
representation -- is a real observation, not a claim about which
personality is inherently harder to model.

## 13. Data-completeness stratification

Every window in the synthetic dataset has `completeness == 1.0` (no
missing values were ever injected into the generator), so only a
"high" completeness band is populated; the stratification code itself
is implemented and tested and is ready the moment non-trivial
missingness exists in a dataset. Figure:
`release/figures/08_error_by_completeness.png`.

## 14. Feature importance (gain-based)

(`release/results/feature_importance.csv`, XGBoost's own
`get_score(importance_type="gain")`, averaged across the sin and cos
models; figure: `release/figures/07_feature_importance.png`)

| Rank | Feature | Mean gain importance |
|---|---|---|
| 1 | `screen_end_day_6_sin` | 4.322 |
| 2 | `screen_end_day_5_sin` | 1.777 |
| 3 | `screen_end_day_1_sin` | 1.149 |
| 4 | `screen_end_day_4_sin` | 1.127 |
| 5 | `last_meal_day_6_cos` | 1.055 |
| 6 | `screen_end_day_3_sin` | 0.812 |
| 7 | `meq_normalized` | 0.526 |
| 8 | `screen_end_day_2_sin` | 0.479 |
| 9 | `last_meal_day_5_cos` | 0.472 |
| 10 | `last_meal_day_6_sin` | 0.406 |

Evening screen end time (especially the most recent window day) and
last meal timing dominate, with MEQ also prominent. **This indicates
predictive association within the synthetic data-generating system --
not a causal claim.** The synthetic generator was itself built to make
evening screen exposure and meal timing drive `current_DLMO`, so
XGBoost recovering that association is an expected pipeline sanity
check, not independent scientific evidence about real human circadian
biology.

## 15. SHAP diagnostics

(`release/results/shap_importance.csv`, `shap.TreeExplainer` on a
300-row sample of the held-out test set, mean absolute SHAP value, sin
and cos models averaged)

| Rank | Feature | Mean \|SHAP\| |
|---|---|---|
| 1 | `meq_normalized` | 0.0369 |
| 2 | `screen_end_day_6_sin` | 0.0265 |
| 3 | `screen_end_day_1_sin` | 0.0211 |
| 4 | `screen_end_day_5_sin` | 0.0168 |
| 5 | `screen_end_day_4_sin` | 0.0154 |
| 6 | `screen_end_day_3_sin` | 0.0132 |
| 7 | `social_jetlag_mean_minutes` | 0.0131 |
| 8 | `last_meal_day_6_cos` | 0.0123 |
| 9 | `screen_end_day_2_sin` | 0.0122 |
| 10 | `msfsc_cos` | 0.0110 |

Broadly consistent with the gain-based ranking (evening screen timing
and MEQ dominate both), with SHAP additionally surfacing
`social_jetlag_mean_minutes` and `msfsc_cos` more prominently -- a
reminder that gain-based importance (average split gain) and SHAP
(average marginal contribution to individual predictions) answer
subtly different questions and should be read together, not
interchangeably. As with section 14: association within the synthetic
system, not a causal or clinical claim. (No new SHAP figure was
generated for this release; `release/figures/07_feature_importance.png`
and this table are the release's SHAP/importance record. Generating an
additional plot against the frozen model artifact was considered
optional for this phase and was not judged to add material information
beyond this table.)

## 16. Comparison against project success targets

| Tier | MAE target | % within 60 target | Met? |
|---|---|---|---|
| Minimum | < 60 min | > 70% | Yes (24.47 min, 93.73%) |
| Good | < 45 min | > 80% | Yes |
| **Excellent** | **< 35 min** | **> 85%** | **Yes** |

**Excellent tier reached**, on this synthetic held-out set, under the
untuned baseline hyperparameter configuration. No hyperparameter
search, no test-set-directed tuning, and no metric manipulation were
used to reach this result -- it is the first and only evaluation of
the final model against the held-out test participants.

## 17. Limitations

- **Synthetic data only, no real-human DLMO ground truth.** Every
  metric in this document describes performance against data
  generated by the project's own generative model -- a model built
  using some of the same behavioral-effect assumptions the XGBoost
  model is now "discovering." Strong performance here partly reflects
  the generator and predictor sharing a common synthetic world, not
  independent validation against real biology. **No component of
  CircadianIQ has ever been evaluated against a real human DLMO
  measurement, and 93.73% (or any other figure here) must never be
  cited as human/clinical accuracy.**
- **`feature_manifest_version` label inconsistency** (section 3): the
  trained model's own metadata records `"phase4-v1"`; the current code
  constant is `"1.0.0"`. Verified to be a version-label naming issue,
  not a feature-set drift -- but a downstream consumer reading only
  the code constant without this document could be misled about which
  manifest generation actually produced this model's training data.
- **Version provenance beyond the model itself is incomplete**
  (Phase 17 audit §22, `docs/final_database_design.md` limitation #2):
  `circadian_labels.training_run_id` gives structured, queryable
  provenance for the XGBoost model version used on a given prediction
  row, but pipeline/fusion/state/alignment/recommendation config
  versions live only inside an opaque JSON blob
  (`alignment_results.component_snapshot`) or nowhere at all
  (`contributor_results`, `intervention_log`). A prediction's model
  version is traceable; the full configuration context around it is
  only partially traceable.
- **Completeness stratification is untested by real missingness**
  (section 13) -- the synthetic dataset has none.
- **No hyperparameter tuning was performed**, per the project brief --
  reported numbers reflect an engineering-starting-point
  configuration, not a ceiling on what XGBoost could achieve on this
  data.
- **Personality/chronotype performance differences correlate with
  training-set representation** (sections 11-12); this document does
  not, and cannot, cleanly separate "harder to predict" from "less
  training data" with a single training run.
- **Native multi-output XGBoost was not used** despite being available
  in the installed version (section 6) -- a documented choice, not an
  oversight.

## 18. Reproducibility

Given the same database snapshot, feature manifest, split seed (2025),
and hyperparameters, training is deterministic: `numpy.default_rng`
(participant split), `XGBRegressor(random_state=42)` (tree
construction), and `GroupKFold` (deterministic given fixed group/row
order) leave no unseeded randomness in the pipeline. Verified by two
full pipeline runs on an identical fixture dataset producing identical
split assignments and metrics to floating-point tolerance. Documented
remaining nondeterminism: XGBoost's `n_jobs=-1` multi-threaded
histogram construction can, in principle, introduce tiny
floating-point-order differences on different hardware/thread counts;
not observed to change decoded-hour metrics at the precision reported
here, but exact bit-for-bit reproduction across different machines is
not guaranteed. Phase 17's independent reproducibility audit ran two
full pipeline executions off an identical DB snapshot and confirmed
every downstream component (XGBoost prediction, state prediction,
fused DLMO, alignment, contributors, recommendation) matched exactly.

## Source artifacts referenced by this document

- `release/results/model_metrics.csv`, `baseline_comparison.csv`,
  `chronotype_metrics.csv`, `personality_metrics.csv`,
  `feature_importance.csv`, `shap_importance.csv`, `cv_per_fold.csv`,
  `test_summary.csv`
- `release/figures/01_actual_vs_predicted_circular.png`,
  `02_absolute_error_distribution.png`,
  `03_signed_error_distribution.png`,
  `04_predicted_vs_actual_scatter.png`,
  `05_performance_by_chronotype.png`,
  `06_performance_by_personality.png`,
  `07_feature_importance.png`, `08_error_by_completeness.png`
- `models/model_metadata_v1.json`,
  `models/xgboost_dlmo_sin_v1.pkl`, `models/xgboost_dlmo_cos_v1.pkl`
  (frozen; not retrained or modified for this release)
- `docs/model_training_and_validation.md` (Phase 5 detailed record),
  `docs/system_validation_and_audit.md` (Phase 17 audit),
  `release/version_manifest.json`

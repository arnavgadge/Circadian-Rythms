# CircadianIQ Model Training and Validation (Phase 5)

> **This model is trained and validated on synthetic data.** Its
> performance does **not** prove equivalent performance on real human
> DLMO data. Every metric below reads "on the synthetic held-out
> participant set" implicitly, and that qualifier should never be
> dropped when this work is cited or reused.

## 1. Problem definition

Predict the target day's `current_DLMO` from the six previously
completed days of a participant's behavior (Phase 4's 68-feature,
six-day window vector). This is a regression problem over a **circular**
target (a clock time), solved as two independent regressions --
`sin(DLMO)` and `cos(DLMO)` -- decoded back to a clock hour after
prediction. This phase trains, cross-validates, and evaluates that
model once; it does not fuse it with anything, run it in production,
or feed its output into alignment/recommendation logic.

## 2. Feature/target contract

- **X**: exactly the Phase 4 manifest, 68 features, unmodified --
  `app.models.sanity.validate_feature_matrix` asserts this before any
  training happens and again that the train/test matrices have
  identical columns.
- **Y**: `target_dlmo_sin`, `target_dlmo_cos` (Phase 4's
  `circadian_labels.fused_dlmo_time`, encoded via
  `app.features.time_encoding.clock_to_sincos`). `app.models.sanity.
  validate_targets` asserts finiteness, valid hour range, unit
  magnitude, no missing values, and participant/date alignment with
  the feature rows before training.
- **Dataset size**: 24,000 windows across 1,000 participants (Phase 4's
  exact output; verified unchanged going into this phase).

## 3. Participant-level splitting

`app.models.splitting.split_participants(participant_ids, test_fraction,
seed)` shuffles participant IDs (never rows) with a seeded RNG and
slices the boundary -- deterministic, so the same seed always
reproduces the same split, and a participant can never land on both
sides. Realized on the full dataset:

- **Split seed**: 2025, **split version**: "v1", **test fraction**: 0.2
- **Train**: 800 participants, 19,200 windows
- **Test**: 200 participants, 4,800 windows
- Verified: `set(train_ids).isdisjoint(test_ids)` (asserted in code and
  in `tests/test_models_splitting.py` / `tests/test_models_training.py`)

The test participants are read exactly once, at the single "held-out
test" step in section 9 below -- never during CV, never during
hyperparameter selection.

## 4. 5-fold GroupKFold

Inside the 800 training participants only: `sklearn.model_selection.
GroupKFold(n_splits=5)`, grouped by `participant_id`, so every window
belonging to a participant lands in exactly one fold. Ordinary
`KFold` (row-based) is never used anywhere in this codebase for model
selection. Each fold: 640 training participants (15,360 windows) / 160
validation participants (3,840 windows) -- confirmed programmatically
per fold (`assert train_groups.isdisjoint(val_groups)` in
`app.models.training.run_grouped_cross_validation`, re-checked by a
dedicated test).

| Fold | Train participants | Val participants | MAE (min) | RMSE (min) | % within 60 min |
|---|---|---|---|---|---|
| 0 | 640 | 160 | 26.57 | 33.63 | 92.27 |
| 1 | 640 | 160 | 24.98 | 32.56 | 92.60 |
| 2 | 640 | 160 | 26.45 | 34.17 | 92.66 |
| 3 | 640 | 160 | 23.32 | 30.38 | 94.35 |
| 4 | 640 | 160 | 24.79 | 31.76 | 93.28 |
| **Mean +/- std** | | | **25.22 +/- 1.20** | **32.50 +/- 1.35** | **93.03 +/- 0.74** |

Low fold-to-fold variance (MAE std of 1.2 minutes on a ~25-minute mean)
indicates the baseline configuration is reasonably stable across
different training participant subsets, on this synthetic dataset.

## 5. Model configuration

Two independent `xgboost.XGBRegressor` models (one for `sin(DLMO)`, one
for `cos(DLMO)`) -- see section 6 for why two independent models rather
than a single multi-output one. Hyperparameters (project brief's own
"engineering starting points", **not** claimed optimal; see
`app.models.config.XGBoostHyperparameters`):

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
The code is structured (`app.models.config.TrainingConfig`) so a later
phase can substitute a tuned `XGBoostHyperparameters` instance without
touching the pipeline logic.

## 6. Target circular encoding

`sin(2*pi*h/24)`, `cos(2*pi*h/24)` for clock hour `h` -- the Phase 4
utility (`app.features.time_encoding.clock_to_sincos`), reused here
rather than reimplemented. Verified empirically before committing to
an architecture: `xgboost==3.4.1`'s `XGBRegressor` was tested with a
raw 2-column target array and **did** fit and predict without error
(some native multi-output support exists in this installed version).
This implementation deliberately does not rely on that: per the
brief's explicit preference for "the simplest reliable implementation"
over an unverified-across-versions native path, and to keep feature
importance / SHAP analysis unambiguous per target component, it trains
**two fully independent `XGBRegressor` models**.

**Decoding a prediction is not the same as decoding a true encoded
value**: nothing constrains a model's raw `(sin, cos)` output to the
unit circle. `app.models.target_encoding.decode_predictions`
normalizes first --

```
r = sqrt(sin^2 + cos^2)
if r > 0: sin_norm, cos_norm = sin/r, cos/r
hour = atan2(sin_norm, cos_norm) -> [0, 24)
```

-- verified by `tests/test_models_target_encoding.py` against both an
inflated (magnitude 2.5) and shrunk (magnitude 0.1) synthetic
prediction vector, confirming the decoded hour is unaffected by
magnitude.

## 7. Error calculation

Every metric is a **circular** difference (`app.models.evaluation.
circular_error_minutes`): `actual - predicted`, shortest signed arc.
23:50 vs. 00:10 is a 20-minute error, confirmed directly by
`tests/test_models_evaluation.py::
test_circular_error_midnight_crossing_is_20_minutes_not_23h40` -- never
the ~23h40m a naive linear subtraction would produce. All CV, test, and
stratified metrics in this document are computed this way, on decoded
clock hours, never on raw sin/cos component error (component MSE does
not correspond to a clock-time error a human would recognize).

## 8. Baseline models

Neither baseline uses sleep-onset timing (which would violate the
anti-circularity design the feature layer itself enforces):

- **Baseline 1 -- participant mean**: predicts each test
  participant's circular mean *training-target* DLMO (from that
  participant's own 24 training windows).
- **Baseline 2 -- MSFsc proxy**: decodes the already-computed
  `msfsc_sin`/`msfsc_cos` features directly as a naive DLMO guess, with
  no learned parameters. MSFsc (corrected free-day sleep midpoint) is
  the one phase-related signal the Phase 4 architecture explicitly
  sanctions as *not* being direct sleep-onset timing, which is why it
  is used here rather than any sleep-timing feature.

All three rows below are computed on the identical 200-participant,
4,800-window held-out test set:

| Model | MAE (min) | % within 60 min |
|---|---|---|
| **XGBoost (this model)** | **24.47** | **93.73** |
| Baseline 1: participant mean | 57.2 | 67.6 |
| Baseline 2: MSFsc proxy | 342.1 | 0.0 |

XGBoost cuts the participant-mean baseline's error by more than half.
The MSFsc baseline is dramatically worse, as expected: it carries a
large, roughly constant offset, because MSFsc measures sleep
*midpoint*, not DLMO -- sleep midpoint is approximately
`sleep_onset + duration/2`, while DLMO is approximately
`sleep_onset - 2h`, a structural ~5.5-6 hour gap between the two
quantities that a non-learned baseline cannot correct for (consistent
with the baseline's observed signed bias of roughly -333 minutes, i.e.
about 5.5 hours). This is the expected, correct behavior of that
baseline, not a bug: it demonstrates why a raw proxy is not enough and
a learned phase correction is needed.

## 9. Overall (held-out test) metrics

Computed **exactly once**, on the 200 held-out test participants
(4,800 windows), after final training on all 800 training participants:

| Metric | Value |
|---|---|
| n (windows) | 4,800 |
| MAE | **24.47 min** |
| RMSE | 31.86 min |
| Median absolute error | 19.71 min |
| % within +/-15 min | 39.56% |
| % within +/-30 min | 69.40% |
| % within +/-60 min | **93.73%** |
| % within +/-90 min | 98.67% |
| Signed mean error (bias) | -0.82 min |
| Signed std of error | 31.85 min |
| p90 absolute error | 51.05 min |
| p95 absolute error | 64.99 min |

## 10. Personality-stratified metrics

(200 test participants, 4,800 windows, from the production run.)

| Personality | n participants | n windows | MAE (min) | % within 30 | % within 60 | Bias (min) |
|---|---|---|---|---|---|---|
| Consistent early bird | 14 | 336 | 30.8 | -- | 86.0 | +7.3 |
| Consistent night owl | 14 | 336 | 25.2 | -- | 92.6 | -3.5 |
| Social jetlag student | 50 | 1,200 | 20.6 | -- | 97.2 | -4.2 |
| Chaotic sleeper | 25 | 600 | 29.2 | -- | 89.5 | +6.7 |
| Healthy stable routine | 28 | 672 | 28.9 | -- | 90.2 | +1.2 |
| Screen-heavy user | 46 | 1,104 | 20.3 | -- | 97.4 | -6.0 |
| Late eater | 23 | 552 | 26.4 | -- | 93.1 | +2.9 |

The two most-represented personalities in the population (screen-heavy
user, 18%; social jetlag student, 25%) have the lowest MAE -- consistent
with those groups also having the most *training* examples, not
necessarily with their behavior being intrinsically easier to predict.
Consistent early bird (the smallest group, 8% of the population) has
the highest MAE. This pattern -- performance tracking training-set
representation -- is a real observation worth flagging, not a claim
about which personality is inherently harder to model.

## 11. Chronotype-stratified metrics

| Chronotype | n participants | n windows | MAE (min) | % within 60 | Bias (min) |
|---|---|---|---|---|---|
| Early | 55 | 1,320 | 30.0 | 89.5 | -11.3 |
| Intermediate | 119 | 2,856 | **20.0** | **97.8** | -0.3 |
| Late | 26 | 624 | 33.1 | 84.1 | +18.9 |

Intermediate chronotype (59% of the population, and the chronotype
with the smallest source-backed DLMO standard deviation, 12 minutes --
see `docs/synthetic_data_generation.md`) is predicted noticeably better
than Early or Late. Late chronotype has both the worst MAE and the
largest positive bias (+18.9 min, i.e. the model tends to predict too
early for Late-chronotype participants) -- again plausibly explained by
Late being both the smallest population share (14%) and the
chronotype with the largest source-backed DLMO spread (54-minute SD).
The model does **not** perform equally across chronotypes, and this
should inform any later phase that consumes its predictions.

## 12. Data-completeness-stratified metrics

Using the existing Phase 4 `completeness` field (bucketed: high >=0.95,
moderate 0.80-0.95, low <0.80) -- the brief's existing confidence/
completeness definition, not a new competing system, and no production
confidence-fusion logic is implemented here.

| Completeness band | n participants | n windows | MAE (min) | % within 60 | Bias (min) |
|---|---|---|---|---|---|
| High | 200 | 4,800 | 24.47 | 93.73 | -0.82 |
| Moderate | 0 | 0 | -- | -- | -- |
| Low | 0 | 0 | -- | -- | -- |

Every window in the Phase 3 synthetic dataset has `completeness ==
1.0` (no missing values were ever injected into the generator), so
only the "high" band is populated. This phase cannot say anything
about how missingness affects model performance on *this* dataset --
that question needs either a deliberately-degraded synthetic dataset
or real-world data with genuine gaps, neither of which exists yet. The
stratification code itself is implemented and tested
(`app.models.training._completeness_band`, exercised by the training
pipeline tests) so it is ready the moment non-trivial missingness
exists in a dataset.

## 13. Feature importance

Gain-based importance (XGBoost's own `get_score(importance_type="gain")`,
averaged across the sin and cos models), top 10:

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

Evening screen end time (especially the most recent day, day 6) and
last meal timing dominate gain-based importance, with MEQ also
prominent. **This indicates predictive association within the synthetic
data-generating system -- not a causal claim.** The synthetic generator
(Phase 3) was itself built to make evening screen exposure and meal
timing drive `current_DLMO`, so XGBoost recovering that association is
an expected sanity check that the pipeline works, not independent
scientific evidence that screen time causes phase delay in real humans.

## 14. SHAP diagnostics

Computed via `shap.TreeExplainer` on a 300-row sample of the held-out
test set (mean absolute SHAP value, sin and cos models averaged), top
10:

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
| 10 | `msfsc_cos` | 0.011 |

Broadly consistent with the gain-based ranking (evening screen timing
and MEQ dominate both), with SHAP additionally surfacing
`social_jetlag_mean_minutes` and `msfsc_cos` more prominently than
gain-based importance did -- a reminder that the two importance
measures answer subtly different questions (average split gain vs.
average marginal contribution to individual predictions) and should be
read together, not interchangeably. As with section 13: association
within the synthetic system, not a causal or clinical claim.

## 15. Final held-out test result

**MAE = 24.47 minutes, RMSE = 31.86 minutes, 93.73% within +/-60
minutes, on the synthetic held-out participant set (200 participants,
4,800 windows, never seen during CV or final training).**

## 16. Comparison against project success targets

| Tier | MAE target | % within 60 target | Met? |
|---|---|---|---|
| Minimum | < 60 min | > 70% | Yes (24.47 min, 93.73%) |
| Good | < 45 min | > 80% | Yes |
| **Excellent** | **< 35 min** | **> 85%** | **Yes** |

**Result: Excellent tier reached**, on this synthetic held-out set,
under the baseline (untuned) hyperparameter configuration. No
hyperparameter search, no test-set-directed tuning, and no metric
manipulation were used to reach this result -- it is the first and
only evaluation of the final model against the held-out test
participants. These success targets were defined as project targets,
not guarantees, and reaching "excellent" on synthetic data is not
evidence of reaching it on real human data (see the notice at the top
of this document).

## 17. Limitations

- **Synthetic data only.** All numbers in this document describe
  performance against data generated by Phase 3's own generative model
  -- a model built using some of the same behavioral-effect assumptions
  the XGBoost model is now "discovering." Strong performance here
  partly reflects the generator and predictor sharing a common
  synthetic world, not independent validation against real biology.
- **Completeness stratification is untested by real missingness** (see
  section 12) -- the synthetic dataset has none.
- **The MSFsc-baseline interpretation is a judgment call.** The brief's
  exact phrase ("the most recent available non-circular phase proxy
  allowed by the feature architecture") was ambiguous; MSFsc was
  chosen as the most defensible available reading, and is documented
  as such rather than presented as the only possible interpretation.
- **No hyperparameter tuning was performed**, per the brief -- the
  reported numbers reflect the project's engineering-starting-point
  configuration, not a ceiling on what XGBoost could achieve on this
  data.
- **Personality/chronotype performance differences correlate with
  training-set representation** (sections 10-11); this document does
  not, and cannot, cleanly separate "harder to predict" from "less
  training data" with a single training run.
- **Native multi-output XGBoost was not used** despite being available
  in the installed version (section 6) -- a reasonable, documented
  choice, but a later phase revisiting this could re-evaluate whether
  the native path offers meaningful efficiency gains without losing
  per-target interpretability.

## Reproducibility

Given the same database snapshot, feature manifest, split seed
(2025), and hyperparameters, training is deterministic: `numpy`'s
`default_rng` (participant split), `XGBRegressor(random_state=42)`
(tree construction), and `GroupKFold` (deterministic given fixed group/
row order) leave no unseeded randomness in the pipeline. Verified by
`tests/test_models_training.py::
test_reproducibility_same_seed_same_config_gives_equivalent_metrics`
(two full pipeline runs on the same fixture dataset produce identical
split assignments and metrics to floating-point tolerance). Documented
remaining nondeterminism: XGBoost's `n_jobs=-1` multi-threaded
histogram construction can, in principle, introduce tiny
floating-point-order differences on different hardware/thread counts;
this has not been observed to change the decoded-hour metrics at the
precision reported here, but exact bit-for-bit reproduction across
different machines is not guaranteed.

## Module map

```
app/models/
    config.py            SplitConfig, CVConfig, XGBoostHyperparameters, SuccessTargets, TrainingConfig
    target_encoding.py    clock_to_sincos/sincos_to_clock (re-exported) + normalize_sincos/decode_predictions
    splitting.py           split_participants() + SplitResult (JSON-persistable)
    evaluation.py           circular_error_minutes, compute_metrics, stratified_metrics, check_success_targets
    baselines.py            predict_baseline_participant_mean, predict_baseline_msfsc_proxy
    xgboost_model.py         DualComponentXGBModel (two independent XGBRegressors)
    sanity.py                validate_feature_matrix, validate_targets
    cohorts.py               attach_participant_cohorts (chronotype/personality join, diagnostic only)
    training.py               run_training_pipeline, run_grouped_cross_validation, persist_training_run
    model_registry.py         next_version, save_model_artifacts, load_model_artifacts, ModelMetadata
    diagnostics.py            the 8 required diagnostic plots

app/scripts/train_model.py   CLI entry point
```

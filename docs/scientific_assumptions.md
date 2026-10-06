# CircadianIQ Scientific Assumption Inventory (Phase 18 release consolidation)

**Release:** v1.0.0-research-demo.

This document is the complete, release-final inventory of every
meaningful numerical assumption in CircadianIQ, classified as:

- **LITERATURE-BACKED (A)** -- the value is taken from a source cited
  in the project's own documentation (`CircadianIQ_Project_Document.docx`
  section 5) or in the code's own docstring/comment. **No literature
  source is fabricated anywhere in this document**: if a constant's own
  code does not cite a real source, it is classified as a PROJECT
  MODELING ASSUMPTION, never as literature-backed, regardless of how
  scientifically plausible the value looks.
- **PROJECT MODELING ASSUMPTION (B)** -- a deliberate choice about how
  a biological/behavioral relationship should be represented in this
  system (e.g. a curve shape, a bound, a weighting), made without a
  cited external source, but intended to represent something about the
  domain (not merely an implementation convenience).
- **ENGINEERING CHOICE (C)** -- a value chosen for numerical/engineering
  reasons (stability, threshold definition, UI-legible bucketing) with
  no claim to model anything biological.

This document is built on, and extends, Phase 17's audit inventory
(`docs/system_validation_and_audit.md` section 26, "Scientific-
assumption inventory," already verified via file:line citations, not
merely read-through). It adds the synthetic chronotype/personality
population distributions and every other numerical assumption named in
the Phase 18 brief's example list that was not already in the Phase 17
table. Every row's Source-if-any column is either a real citation
found in the code, or explicitly blank.

**No constant in the system is classified (A) literature-backed with an
actual in-code cited source for values invented for engineering
convenience** -- confirmed directly by reading `app/personalization/config.py:3-5`
and `app/safety/config.py:3-11`, both of which already explicitly
self-disclaim literature-validation status in their own docstrings.

## Master table

| Parameter | Value/Range | Component | Classification | Source-if-any | Reason | Caveat |
|---|---|---|---|---|---|---|
| Chronotype population proportions | early 27% / intermediate 59% / late 14% | `app/synthetic/config.py:SourceBackedAssumptions.chronotype_population_proportions` (`:47-49`) | **A -- Literature-backed** | PMC6595939; Wittmann et al., *Chronobiology International* 2006 | Cited in-code as the population split used to generate synthetic chronotype labels | Used to shape the *synthetic* population only; it is not a claim about the real deployment population |
| DLMO mean clock hour by chronotype | early 20:24 / intermediate 21:31 / late 22:56 | `app/synthetic/config.py:SourceBackedAssumptions.dlmo_mean_hour_by_chronotype` (`:53-59`) | **A -- Literature-backed** | Hunger et al., "Behavioural Parameters of Circadian Rhythm" (PMC10743549) | Anchors each synthetic chronotype's intrinsic DLMO distribution | Applied once at synthetic-generation time; not re-derived from any real assay |
| DLMO SD by chronotype | early 42 min / intermediate 12 min / late 54 min | `app/synthetic/config.py:SourceBackedAssumptions.dlmo_sd_hours_by_chronotype` (`:61-63`) | **A -- Literature-backed** | Hunger et al. (PMC10743549) | Spread of the synthetic per-participant DLMO draw | Intermediate's narrow SD (12 min) is why intermediate-chronotype test windows are predicted best (see `docs/final_ml_methodology.md` section 11) |
| Sleep onset after DLMO | +2.0h, noise SD 1.0h | `app/synthetic/config.py:SourceBackedAssumptions.sleep_onset_after_dlmo_hours` / `sleep_onset_dlmo_noise_sd_hours` (`:69-72`) | **A -- Literature-backed** | Frontiers in Neurology (2010); Oxford *Sleep* journal (zsab126), r=0.89 in cited literature | Anchors each synthetic participant's stable baseline sleep-onset trait to their intrinsic DLMO, once, at generation time | Applied only once per participant at generation time -- never re-applied against the evolving `current_DLMO`, specifically to avoid a behavior<->biology feedback loop |
| Morning light -> phase advance anchors | no-light delay 10-20 min; high-light advance 15-45 min | `app/synthetic/config.py:SourceBackedAssumptions.morning_light_*_range` (`:76-80`) | **A -- Literature-backed** (anchor points only) | PMC10594521; PubMed 25620199 | Calibration anchors for the synthetic saturating-response curve | The curve *shape* between these anchors (`morning_light_saturation_tau_minutes=22.0`) is a synthetic interpolation, classified separately below as (B) |
| Evening screen -> phase delay anchors | moderate 10-30 min; heavy 20-60 min | `app/synthetic/config.py:SourceBackedAssumptions.evening_screen_*_range` (`:83-86`) | **A -- Literature-backed** (anchor points only) | PMC12668929; PMC10594521 | Calibration anchors for the synthetic saturating-response curve | Curve shape (`evening_screen_saturation_tau_minutes=120.0`) is a synthetic interpolation, (B) below |
| Social jetlag distribution | mean 1.0h, SD 0.75h, range 0-3h | `app/synthetic/config.py:SourceBackedAssumptions.social_jetlag_*` (`:90-93`) | **A -- Literature-backed** | PMC6595939; Wittmann et al. 2006 | Population distribution of the synthetic social-jetlag draw | -- |
| Late meal (after 9pm) -> phase delay | 15-30 min | `app/synthetic/config.py:SourceBackedAssumptions.late_meal_after_9pm_delay_minutes_range` (`:96-97`) | **A -- Literature-backed** | PMC6471585 | Anchor for the synthetic late-meal effect | -- |
| MEQ instrument range | 16-86 | `app/synthetic/config.py:SourceBackedAssumptions.meq_score_min/max` (`:101-107`) | **A -- Literature-backed** | Horne & Ostberg (1976), Morningness-Eveningness Questionnaire | Property of the published instrument itself | Not a project-specific finding; simply the standard instrument's scale bounds |
| Behavioral personality population proportions | early bird 8% / night owl 10% / social jetlag student 25% / chaotic sleeper 12% / healthy stable 15% / screen-heavy 18% / late eater 12% | `app/synthetic/config.py:SyntheticAssumptions.personality_proportions` (`:120-129`) | **B -- Project modeling assumption** | none (explicitly noted as a synthetic design choice in the module docstring) | Shapes the synthetic population's behavioral archetypes | Directly explains the training-set-representation pattern seen in `docs/final_ml_methodology.md` section 12 (screen-heavy user and social-jetlag student are best-predicted partly because they are the largest groups) |
| Participant sensitivity multipliers (light/screen/meal) | means 1.0, SDs 0.20/0.15/0.18, clip (0.3, 2.0) | `app/synthetic/config.py:SyntheticAssumptions.*_sensitivity_*` (`:132-138`) | **B -- Project modeling assumption** | none | Per-participant variability in how strongly each behavior affects synthetic phase | No source found for these specific SDs |
| Exercise/caffeine phase effects | exercise +-8 min max; caffeine 10 min max delay | `app/synthetic/config.py:SyntheticAssumptions.exercise_*`, `caffeine_late_delay_minutes_max` (`:141-153`) | **B -- Project modeling assumption**, directionality plausibility only | none (module docstring explicitly states "no project source found," directionality follows general chronobiology plausibility) | Deliberately kept small/illustrative | Explicitly disclaimed in-code as having no cited source for magnitude |
| Saturating-curve time constants (light/screen/meal) | 22 min / 120 min / 1h | `app/synthetic/config.py:SyntheticAssumptions.*_saturation_tau_*` (`:154-158`) | **C -- Engineering choice** | none | Controls *how* the response curve interpolates between the literature-cited anchor points above | The anchor values are cited; this shape parameter is not |
| Interaction-effect multipliers (light/screen/meal combos) | 1.25 / 0.75 / 0.5 / 1.3 | `app/synthetic/config.py:SyntheticAssumptions.interaction_*` (`:161-171`) | **B -- Project modeling assumption** | none (explicitly synthetic per project brief) | Models plausible interaction directions between simultaneous behaviors | No magnitude source |
| Daily behavioral shift clip | -90 to +60 min | `app/synthetic/config.py:SyntheticAssumptions.daily_shift_clip_minutes` (`:178`) | **C -- Engineering choice** | none (explicitly "a simulation-stability constraint, not a physiological maximum") | Prevents runaway single-day shifts in the generator | -- |
| Adapted-DLMO daily pull fractions (behavior/intrinsic) | ~1%/day, ~0.5%/day | `app/synthetic/config.py:SyntheticAssumptions.adapted_daily_pull_to_*_fraction` (`:181-182`) | **B -- Project modeling assumption** | none | Synthetic three-layer DLMO state-update rates | Mirrored (and re-exposed) as production state-engine constants below |
| Adapted-DLMO bound from intrinsic | +-2.0h | `app/state/config.py:49`; `app/synthetic/config.py:181-184` | **B -- Project modeling assumption** | none | How far the slow-adapting DLMO layer may drift from the stable intrinsic value | Confirmed by Phase 17 audit (state-engine audit, section 10) to hold under 180-day trajectories |
| Current-DLMO bound from intrinsic | +-3.0h | `app/state/config.py:57` | **B -- Project modeling assumption** | none | How far the fast/dynamic DLMO layer may drift | Same, confirmed by Phase 17 audit |
| Current-DLMO daily pull-to-adapted rate | 0.5 | `app/state/config.py:54` | **C -- Engineering choice** | none | Blend rate of the fast layer toward the adapted layer each day | -- |
| Adaptation rate (adapted layer, production state engine) | 0.01/day | `app/state/config.py:43` | **B -- Project modeling assumption** | none | Rate at which the adapted-DLMO layer moves toward observed behavior | -- |
| Intrinsic recovery rate | 0.005/day | `app/state/config.py:46` | **B -- Project modeling assumption** | none | Rate at which the adapted layer drifts back toward intrinsic absent disturbance | -- |
| Daily state continuity cap | 60 min/day | `app/state/config.py:74` | **C -- Engineering choice** | none | Caps how far the fused DLMO may move in one day, for output stability | -- |
| DLMO fusion base weights by confidence tier | HIGH 0.65/0.35, MODERATE 0.55/0.45, LOW 0.40/0.60, VERY_LOW 0.20/0.80 (XGBoost/state) | `app/fusion/config.py:64-68` | **B -- Project modeling assumption** | none | How much to trust the ML model vs. the mechanistic state model as data confidence degrades | -- |
| Fusion disagreement thresholds | 20/45/75 min | `app/fusion/config.py:72` | **C -- Engineering choice** | none | Boundaries between disagreement regimes | -- |
| Fusion continuity caps by disagreement regime | 60/45/30/20 min | `app/fusion/config.py:85-92` | **C -- Engineering choice** | none | Tightens the daily movement cap as XGBoost/state disagree more | -- |
| Confidence penalties by disagreement regime | 0 / -8 / -18 / -30 | `app/fusion/config.py:99-106` | **B -- Project modeling assumption** | none | Penalizes displayed confidence when the two models disagree | -- |
| Confidence label thresholds | 80 / 60 / 40 | `app/fusion/config.py:109` | **C -- Engineering choice** (explicitly self-documented as such) | none, self-disclaimed | HIGH/MODERATE/LOW/NO_PREDICTION confidence bands | `app/safety/config.py:3-11` explicitly states these are not clinical thresholds |
| Data-completeness no-prediction threshold | 0.5 | `app/fusion/config.py:112` | **C -- Engineering choice** | none | Below this completeness, no prediction is emitted rather than a low-confidence guess | -- |
| Alignment phase/behavioral split | 60% / 40% | `app/alignment/config.py:30-31` | **B -- Project modeling assumption** | none | Overall alignment-score weighting between phase-based and behavior-based components | -- |
| Alignment behavioral sub-weights | 25/25/20/15/15 (sleep consistency / morning light / evening screen / meals / social jetlag) | `app/alignment/config.py:34-38` | **B -- Project modeling assumption** | none | Relative importance of each behavioral component | -- |
| Phase-to-sleep offset | +2.0h (ideal sleep onset = fused DLMO + offset) | `app/alignment/config.py:43`; used in `app/alignment/ideal_sleep.py:3,20` | **B -- Project modeling assumption** | none (module docstring explicitly labels this a project modeling assumption) | Derives an "ideal" sleep-onset clock time from the fused DLMO for the alignment/UI display | Explicitly documented in-code as a project assumption, not a cited clinical offset (distinct from the *literature-backed* `sleep_onset_after_dlmo_hours=2.0` used only inside the Phase 3 synthetic generator -- the two constants share a value by design but serve different, separately-versioned components) |
| Contributor formula weights | 60% phase effect / 40% alignment deficit | `app/contributors/config.py:19-20` | **B -- Project modeling assumption** | none | How contributor signals are ranked | -- |
| Recommendation severity bands | 80/60/40 | `app/recommendations/config.py:29-32` | **C -- Engineering choice** | none | Maps alignment score to a severity tier for recommendation selection | -- |
| Recommendation severity weight pairs | 0.55/0.45 .. 0.20/0.80 | `app/recommendations/config.py:35-40` | **B -- Project modeling assumption** | none | Blends contributor signal strength vs. severity as severity rises | -- |
| Graduated target fraction | 0.50 | `app/recommendations/config.py:62` | **C -- Engineering choice** | none | Fraction of the full behavioral change asked for in a single graduated recommendation step | Confirmed by Phase 17 audit (section 14) to compute sane clock times under midnight-crossing/boundary construction |
| Feasibility weights (compliance/difficulty/failure penalty) | 0.30/0.25/0.20 | `app/recommendations/config.py:74-82` | **C -- Engineering choice** | none | Scores candidate interventions for feasibility | -- |
| Personalization: ranking-phase threshold | 3 obs / 3 weeks | `app/personalization/config.py:18-19` | **C -- Engineering choice**, explicitly self-disclaimed | none, self-disclaimed | Minimum evidence before moving from "literature" to "personal ranking" | `app/personalization/config.py:3-5` states this is "a project engineering graduation rule, not literature-backed" |
| Personalization: effect-model-phase threshold | 14 obs / 6 weeks | `app/personalization/config.py:22-23` | **C -- Engineering choice**, explicitly self-disclaimed | none, self-disclaimed | Minimum evidence before fitting a personal linear effect model | Same self-disclaimer as above |
| Personalization: adaptive-policy-phase threshold | 42 obs / 12 weeks | `app/personalization/config.py:26-27` | **C -- Engineering choice**, explicitly self-disclaimed | none, self-disclaimed | Minimum evidence before switching to bandit-driven adaptive selection | Same self-disclaimer as above |
| Personalization blend weights | 0.40 personal / 0.60 literature | `app/personalization/config.py:40-41` | **C -- Engineering choice** | none | Blends a participant's own learned effect with the literature default during transition | -- |
| Safety: minimum observations for a flag | 10 | `app/safety/config.py:30` | **C -- Engineering choice** | none | Floor before any safety pattern can trigger, to avoid flagging on noise | -- |
| Safety: persistent-late-phase threshold | 2:00 AM | `app/safety/config.py:33` | **B -- Project modeling assumption**, explicitly NOT a clinical threshold | none, self-disclaimed | Screening threshold for a "persistently very late phase" flag | `app/safety/config.py:11` explicitly disclaims clinical-threshold status |
| Safety: persistent-early-phase threshold | 7:30 PM | `app/safety/config.py:36` | **B -- Project modeling assumption**, explicitly NOT a clinical threshold | none, self-disclaimed | Screening threshold for a "persistently very early phase" flag | Same disclaimer |
| Safety: continuous-drift threshold | 20 min/day | `app/safety/config.py:39` | **C -- Engineering choice** | none | Triggers a "continuous DLMO drift" flag | Verified by Phase 17 audit to correctly ignore alternating-midnight-crossing noise (12-night 23:50/00:10 test case), i.e. the circular-unwrap math behind this threshold is sound |
| Safety: low-alignment-despite-compliance threshold | 45.0 score / 0.70 compliance | `app/safety/config.py:42-43` | **C -- Engineering choice** | none | Triggers a flag when a participant is compliant but not improving | -- |
| XGBoost hyperparameters (n_estimators, max_depth, learning_rate, subsample, colsample_bytree) | 500 / 6 / 0.05 / 0.8 / 0.8 | `app/models/config.py:XGBoostHyperparameters` | **C -- Engineering choice**, explicitly "starting points, not claimed optimal" | none, self-disclaimed | No hyperparameter search was performed, per the project brief | See `docs/final_ml_methodology.md` section 6 |
| Train/test split fraction and seed | 0.2, seed 2025 | `app/models/config.py:SplitConfig` | **C -- Engineering choice** | none | Participant-level split configuration | See `docs/final_ml_methodology.md` section 4 |
| GroupKFold fold count | 5 | `app/models/config.py:CVConfig` | **C -- Engineering choice** | none | Standard cross-validation fold count | -- |
| Confidence-derived data-quality tier thresholds (pipeline) | 0.95 / 0.80 / 0.50 completeness | `app/pipeline/quality.py` (per `docs/daily_inference_pipeline.md` section 6) | **C -- Engineering choice** | none | Maps feature-vector completeness to a `DataQualityTier` for fusion | Same convention already used by `app.scripts.run_fusion_diagnostics` |

## Notes on scope and honesty

- Rows marked (A) are the only ones in this inventory backed by an
  actual citation the code itself carries. Every (A) row above traces
  to `app/synthetic/config.py:SourceBackedAssumptions`, which is the
  only module in the codebase whose docstring claims a literature
  source (from `CircadianIQ_Project_Document.docx` section 5, in turn
  citing the papers named per field). This code has not independently
  re-verified those underlying papers; it treats the project's own
  document as the source of record, per the project's own stated
  policy of referencing documentation accurately rather than
  re-deriving or fabricating citations.
- All (A) rows describe **synthetic-population generation** parameters
  only -- they calibrate how the Phase 3 generator produces training/
  test data, not a claim that any live production output has been
  validated against the cited literature.
- Every (B) and (C) row above was cross-checked against the actual
  `app/*/config.py` source to confirm no citation exists in that
  module before being classified as non-literature-backed; several
  modules (`app/personalization/config.py`,
  `app/safety/config.py`) explicitly self-disclaim
  literature-validation status in their own docstrings, which is the
  correct posture and was verified by Phase 17's audit, not just
  trusted at face value.
- This inventory is a superset of, and remains consistent with,
  Phase 17's audit table (`docs/system_validation_and_audit.md`
  section 26) -- no classification in that table was changed here;
  rows were only added.

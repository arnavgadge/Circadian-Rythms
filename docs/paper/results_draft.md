# Results (Draft)

**Status: draft.** This document is a methodology/results draft toward an eventual IEEE-style paper; it is not a finished or submitted manuscript.

**Release version:** v1.0.0-research-demo. **Phase 17 audit status:** CONDITIONAL PASS.

> **All results below describe performance against CircadianIQ's own synthetic generative model.** This system has **never** been validated against real human DLMO measurements. No number in this document is a clinical, diagnostic, or real-world accuracy claim.

---

## 1. Evaluation Setup

All results below are computed on a strict participant-held-out split of the Phase 3 synthetic dataset: 800 participants (19,200 windows) for training and 5-fold `GroupKFold` cross-validation, and 200 participants (4,800 windows) held out entirely from training and touched exactly once for final evaluation. Full per-metric CSVs and figures are provided in `release/results/` and `release/figures/` and are cited by relative path below rather than restated in full; see those files for complete supporting detail.

No p-values, confidence intervals over the held-out test metrics, or other formal statistical significance tests were computed for any result in this section — see `limitations_draft.md` for the full statement on this point.

## 2. Held-Out Test Set Performance

On the 200-participant, 4,800-window held-out synthetic test set (computed exactly once):

| Metric | Value |
|---|---|
| MAE | 24.47 min |
| RMSE | 31.86 min |
| Median absolute error | 19.71 min |
| Signed bias | -0.82 min |
| p90 absolute error | 51.05 min |
| p95 absolute error | 64.99 min |
| Within ±15 min | 39.56% |
| Within ±30 min | 69.40% |
| Within ±60 min | 93.73% |
| Within ±90 min | 98.67% |

**Headline result:** 93.73% of held-out synthetic test windows were within ±60 minutes.

Full metric detail is provided in `../../release/results/model_metrics.csv` and `../../release/results/test_summary.csv`. Supporting figures: predicted-vs-actual circular comparison (`../../release/figures/01_actual_vs_predicted_circular.png`), absolute error distribution (`../../release/figures/02_absolute_error_distribution.png`), signed error distribution (`../../release/figures/03_signed_error_distribution.png`), and a predicted-vs-actual scatter (`../../release/figures/04_predicted_vs_actual_scatter.png`).

## 3. Cross-Validation Stability

5-fold `GroupKFold` cross-validation, grouped by participant, restricted to the 800 training participants (never touching the held-out test set):

| Metric | Value |
|---|---|
| MAE | 25.22 ± 1.20 min |
| RMSE | 32.50 ± 1.35 min |
| Within ±60 min | 93.03% ± 0.74% |

These figures are close to the held-out test set result (§2), indicating the model's performance is stable across folds and not an artifact of one particular train/test partition. Per-fold detail is provided in `../../release/results/cv_per_fold.csv`.

## 4. Baseline Comparison

Two non-learned baselines were computed on the identical held-out test set to contextualize the XGBoost result:

| Model | MAE | Within ±60 min |
|---|---|---|
| XGBoost (this work) | 24.47 min | 93.73% |
| Participant-mean baseline | 57.2 min | 67.6% |
| MSFsc-proxy baseline | 342.1 min | 0.0% |

The participant-mean baseline predicts each held-out participant's own mean training-period DLMO. The MSFsc-proxy baseline predicts DLMO directly from the sleep-corrected midpoint of sleep (MSFsc), a measure of sleep midpoint rather than DLMO; its dramatically worse performance reflects the structural ~5.5–6 hour gap between sleep midpoint and DLMO that a non-learned proxy cannot correct for. Full detail is provided in `../../release/results/baseline_comparison.csv`.

## 5. Fusion Diagnostic (Mechanism Check, Not an Accuracy Claim)

A diagnostic run combining the XGBoost estimate with an independent state-engine estimate (see `methodology_draft.md` §5) produced a fused MAE of 12.89 minutes, compared with the XGBoost-alone MAE of 24.47 minutes.

**This number must not be read as evidence that fusion improves real-world DLMO accuracy.** In this synthetic dataset, the state-engine estimate is produced by replaying the exact same state-transition model that generated the ground-truth target in the first place — for this dataset, the state estimate effectively *is* the answer key. The diagnostic therefore demonstrates only that the fusion mechanics (weighting, disagreement handling, continuity constraints) operate as designed; it is a mechanism check on the fusion layer's implementation, not an accuracy result, and it should not be cited as a headline finding alongside the held-out test metrics in §2.

## 6. Stratified Performance

Performance was also examined stratified by chronotype and by behavioral-personality archetype. Detail is provided in `../../release/results/chronotype_metrics.csv` and `../../release/results/personality_metrics.csv`, with corresponding figures at `../../release/figures/05_performance_by_chronotype.png` and `../../release/figures/06_performance_by_personality.png`. Interpretation of these strata is deferred to `discussion_draft.md`.

## 7. Feature Importance

Feature importance (gain-based and SHAP-based) is provided in `../../release/results/feature_importance.csv`, `../../release/results/shap_importance.csv`, and `../../release/figures/07_feature_importance.png`. Interpretation is deferred to `discussion_draft.md`.

## 8. Completeness

Because every window in the synthetic dataset has `completeness == 1.0` by construction (no missingness was injected during generation), an error-by-completeness figure (`../../release/figures/08_error_by_completeness.png`) reflects this uniform-completeness condition rather than a degraded-data evaluation; see `limitations_draft.md` for the absence of a missingness-degraded evaluation.

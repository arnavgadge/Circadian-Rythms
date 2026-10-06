# Limitations (Draft)

**Status: draft.** This document is a methodology/results draft toward an eventual IEEE-style paper; it is not a finished or submitted manuscript.

**Release version:** v1.0.0-research-demo. **Phase 17 audit status:** CONDITIONAL PASS.

---

This section enumerates the limitations most material to interpreting CircadianIQ as a whole, including the three specific gaps identified and deliberately left unresolved by the Phase 17 system-wide adversarial audit. For full detail on any item, see `docs/system_validation_and_audit.md` (the Phase 17 audit report) and `docs/research_methodology.md` §22.

## a. Synthetic-Data-Only Validation

No component of CircadianIQ — feature engineering, the XGBoost model, the state engine, fusion, alignment, contributor ranking, recommendation selection, effectiveness estimation, or personalization — has been validated against real human circadian/DLMO measurements. There is no real-human DLMO ground truth anywhere in this project. All reported metrics describe performance against the project's own synthetic generative model, and the synthetic generator and the trained predictor share common synthetic-world assumptions, so strong synthetic performance is not independent evidence of real-world validity.

## b. Three Phase 17-Documented, Deliberately-Unresolved Limitations

1. **No DB-level uniqueness constraint on `circadian_labels.is_latest`.** The invariant that at most one row per participant/date is marked as the current, authoritative row is enforced only by application discipline — specifically, the inference pipeline's own supersede-then-insert logic — and not by a database-level constraint such as a partial unique index. No incorrect output attributable to this gap was observed during the Phase 17 audit, but the gap itself was left unresolved.

2. **Structured version-provenance columns are incomplete.** Of the full set of configuration/model versions that materially affect a given prediction (pipeline, feature-manifest, model, state, fusion, alignment, contributor, and recommendation config versions), only the XGBoost model version is a directly queryable database column (`circadian_labels.training_run_id`). The remaining versions live only inside an in-memory/JSON diagnostics blob (`AlignmentResult.component_snapshot`) attached to the in-memory result, or are not persisted at all — so reconstructing "exactly which configuration produced this historical row" is not uniformly possible via a simple SQL query today.

3. **`latest_recommendation_id_for_type` is not `as_of_date`-scoped.** This personalization catalogue lookup is a catalogue-versioning gap only: if the recommendation catalogue itself changes over time, a personalization query issued "as of" a past date could see a later catalogue state. This is explicitly **not** a participant-data leak — a dedicated temporal-replay proof in the Phase 17 audit confirmed that participant behavioral data itself is correctly `as_of_date`-scoped everywhere it is read.

## c. `feature_manifest_version` Labeling Inconsistency

The trained model's own persisted metadata (`models/model_metadata_v1.json`) records `"feature_manifest_version": "phase4-v1"`, hardcoded in `app/models/training.py` (line ~345), while the current feature-manifest module reports `FEATURE_MANIFEST_VERSION = "1.0.0"` (`app/features/feature_manifest.py`, line ~204). This is a naming/label inconsistency between two version strings that both refer to the same, unchanged 68-feature manifest. It is **not** evidence that the feature set changed between training and the current codebase, and should not be overstated as a data-integrity problem.

## d. No Statistical Significance Testing

No p-values, confidence intervals over the held-out test metrics, or formal hypothesis tests are computed anywhere in the codebase for the headline model-comparison results (MAE, RMSE, percentile-within-band figures reported in `results_draft.md`). This was confirmed by searching `app/models` and `app/effectiveness` for significance-testing code (`significance`, `p_value`, `p-value`, `scipy.stats`, `ttest`), which found none. The one exception is `app/effectiveness/` (Phase 12, intervention-effectiveness estimation), which computes OLS standard errors and a confidence interval for its own per-participant intervention-effect regression coefficient, via the standard `MSE * (X^T X)^-1` formula. This is a narrow, per-participant regression confidence interval and must not be conflated with, or read as, statistical significance testing of the XGBoost model's headline accuracy — no such test exists.

## e. Fusion-Diagnostic Inflation

The fusion diagnostic reported in `results_draft.md` §5 (fused MAE 12.89 min vs. XGBoost-alone MAE 24.47 min) is inflated by construction: in this synthetic dataset, the state-engine estimate used in fusion is produced by replaying the exact same state-transition model that generated the ground-truth target, so the state estimate effectively *is* the answer key for this dataset. This number must never be presented as evidence that fusion improves real-world DLMO accuracy; it demonstrates only that the fusion mechanism operates as designed.

## f. No Hyperparameter Tuning

The XGBoost hyperparameters used (`n_estimators=500`, `max_depth=6`, `learning_rate=0.05`, `subsample=0.8`, `colsample_bytree=0.8`, `objective=reg:squarederror`) are the project's documented engineering starting point. No hyperparameter search of any kind (grid search, random search, Bayesian optimization, or otherwise) was performed; reported results may not reflect the model's achievable performance under tuning.

## g. No Missingness-Degraded Evaluation

Every window in the synthetic dataset has `completeness == 1.0` by construction — no missing values were ever injected during generation. While the three-tier missing-data fallback chain (window → personal history → population default) is implemented and unit-tested, its end-to-end behavior has never been evaluated against a realistically incomplete dataset.

## h. Prototype API and UI

The FastAPI backend and React/TypeScript dashboard are explicitly documented prototypes: no authentication, authorization, production rate limiting, or CORS/TLS configuration is implemented. Neither is intended for production or public deployment in its current form.

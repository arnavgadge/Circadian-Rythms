# Future Work (Draft)

**Status: draft.** This document is a methodology/results draft toward an eventual IEEE-style paper; it is not a finished or submitted manuscript.

**Release version:** v1.0.0-research-demo. **Phase 17 audit status:** CONDITIONAL PASS.

---

## 1. Real-Human Validation (Top Priority)

The single highest-priority next step is replacing or supplementing the synthetic-data validation described in this draft with real, IRB-approved human behavioral and DLMO measurement data. Every result reported in `results_draft.md` describes performance against CircadianIQ's own synthetic generative model; no result in this work has been checked against real human physiology. Establishing any real-world or clinical-relevance claim would require, at minimum: an IRB-approved study protocol, paired behavioral and laboratory DLMO data collection from real participants, and a re-evaluation of the entire pipeline (feature engineering, model, fusion, alignment, recommendation, and safety layers) against that data — none of which has been attempted to date. This should be considered a prerequisite for any future claim of real-world accuracy, and no other item in this list should be read as a substitute for it.

## 2. Closing the Three Phase 17 Gaps

1. Add a partial unique index (or equivalent database-level constraint) on `circadian_labels` enforcing at most one `is_latest = True` row per `(participant_id, target_date)`, closing the first documented Phase 17 gap at the schema level rather than relying solely on application discipline.
2. Add structured, directly queryable provenance columns for the remaining configuration versions (state, fusion, alignment, contributor, and recommendation config versions) currently reconstructable only from the `AlignmentResult.component_snapshot` JSON diagnostics blob or not persisted at all, closing the second documented Phase 17 gap.
3. Make `latest_recommendation_id_for_type` (and any other catalogue-lookup helper used by personalization) explicitly `as_of_date`-scoped against catalogue effective-dating, closing the third documented Phase 17 gap. Note this is a catalogue-versioning fix only; it does not address any participant-data leak, since none was found.

## 3. Reconciling the `feature_manifest_version` Label

Reconcile the `feature_manifest_version` string persisted by `app/models/training.py` (`"phase4-v1"`) with the value reported by `app.features.feature_manifest.FEATURE_MANIFEST_VERSION` (`"1.0.0"`), so both consistently describe the same 68-feature manifest under one version string, removing the labeling inconsistency documented in `limitations_draft.md` §c.

## 4. Hyperparameter Tuning

Evaluate systematic hyperparameter tuning (grid search, random search, or Bayesian optimization) for the XGBoost model, none of which was performed in this release. This includes re-evaluating whether XGBoost's native multi-output regression path offers meaningful efficiency gains over the current two-independent-model architecture without losing per-target feature-importance interpretability.

## 5. Missingness-Degraded Synthetic Evaluation

Introduce a deliberately-degraded (missing-data-injected) synthetic dataset variant to evaluate model, alignment, and contributor-ranking robustness under realistic missingness end-to-end, rather than relying solely on unit-level fallback-chain tests. The current synthetic dataset has `completeness == 1.0` for every window by construction.

## 6. Production Hardening

Before any deployment beyond local research use, add authentication and authorization, production-appropriate rate limiting, and CORS/TLS configuration to the FastAPI backend, per the documented prototype limitations in `docs/api_architecture.md` and `limitations_draft.md` §h. Formal load and production-scale performance testing (beyond the n=1/10/100 single-machine measurements already recorded in `docs/system_validation_and_audit.md`) should also be performed prior to any deployment at scale.

## 7. Additional Items Noted in the Underlying Documentation

- Seed the optional `PERSONALIZATION_MATURE` demo scenario (requiring roughly 12 weeks / 42+ observations of simulated intervention-logging and compliance-outcome cycles), not included in this release's demo database (see `docs/demo_runbook.md` and `release/demo/demo_scenarios.json`).

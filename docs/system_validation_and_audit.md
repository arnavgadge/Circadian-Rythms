# CircadianIQ System Validation & Audit (Phase 17)

**Date:** 2026-09-09
**Scope:** system-wide adversarial audit across all 16 completed phases (database through UI). No redesign was performed; every fix below is a targeted, minimal correction to a defect the audit itself proved, with a regression test.

## 1. Executive summary

The audit ran 30 numbered checks (database integrity through security/privacy) as executable, adversarial pytest/vitest tests -- not read-throughs -- under `tests/audit/` (backend) and `frontend/src/test/` (UI), plus one standalone measurement script (`scripts/audit_performance.py`). It found and fixed **6 real defects**, all minor-to-moderate severity, none of them a temporal-leakage, participant-leakage, or safety-boundary violation. Two further gaps were found, documented, and deliberately **not** fixed because a proper fix requires a schema-versioning decision beyond a "minimal compatibility fix" (see §27 "Known limitations").

**Final combined test count:** 1006 backend passed / 1 skipped (explicitly gated opt-in test, not silent) / 0 failed, out of 1007 backend tests, plus 60/60 frontend tests, plus a clean `tsc -b && vite build`. Starting baseline before this phase was 658 backend tests / 42 frontend tests -- this phase added 349 new backend audit tests and 18 new frontend audit tests, all passing.

**Release status: CONDITIONAL PASS.** See §29 for the full criteria walkthrough.

## 2. Architecture under test

```
SQL database <-> Python computational pipeline (Phases 2-14)
                        |
              FastAPI application layer (Phase 15)
                        |
              React/TypeScript dashboard (Phase 16)
```

Full pipeline: `READ -> feature engineering -> XGBoost + state engine -> DLMO fusion -> alignment -> contributors -> recommendation -> WRITE (one atomic transaction)`, orchestrated by `app/pipeline/orchestrator.py::run_daily_inference`. Personalization (Phase 13) and intervention effectiveness (Phase 12) run as a separate, explicitly `as_of_date`-scoped offline pipeline (`app/personalization/update.py`) that daily inference only ever *reads* from, never triggers.

## 3. Test inventory

| Area | New file(s) | Tests |
|---|---|---|
| DB integrity (1) | `tests/audit/test_audit_db_integrity.py` | 9 |
| Dataset integrity (2) | `tests/audit/test_audit_dataset_integrity.py` | 13 |
| Temporal leakage (3) | `tests/audit/test_audit_temporal_leakage.py` | included in 32 (see file) |
| Participant leakage (4) | `tests/audit/test_audit_participant_leakage.py` | " |
| Feature contract (5) | `tests/audit/test_audit_feature_contract.py` | " |
| Circular time (6) | `tests/audit/test_audit_circular_time.py` | " |
| State engine (7) | `tests/audit/test_audit_state_engine.py` | 22 |
| DLMO fusion (8) | `tests/audit/test_audit_fusion.py` | 36 |
| Alignment (9) | `tests/audit/test_audit_alignment.py` | 26 |
| Contributors (10) | `tests/audit/test_audit_10_contributors.py` | 7 |
| Recommendations (11) | `tests/audit/test_audit_11_recommendations.py` | 12 |
| Intervention effectiveness (12) | `tests/audit/test_audit_12_effectiveness.py` | 10 |
| Personalization leakage (13) | `tests/audit/test_audit_13_personalization_leakage.py` | 1 (the replay proof) |
| Cold start (14) | `tests/audit/test_audit_14_cold_start.py` | 6 |
| Bandit safety (15) | `tests/audit/test_audit_15_bandit_safety.py` | 6 |
| Confidence (16) | `tests/audit/test_audit_confidence.py` | 18 |
| Safety patterns (17) | `tests/audit/test_audit_safety_patterns.py` | 20 |
| Medical language (18) | `tests/audit/test_audit_medical_language.py` + `frontend/src/test/medicalLanguage.test.ts` | 6 + 2 |
| API contract (19) | `tests/audit/test_audit_api_contract.py` | 15 |
| UI/API contract (20) | `frontend/src/test/domainComputationGuard.test.ts` + `frontend/src/test/confidenceSafetyStates.test.tsx` | 16 |
| Failure injection (23) | `tests/audit/test_audit_failure_injection.py` | 11 |
| Golden E2E (28) | `tests/audit/test_audit_golden_participant.py` | 5 |
| Property-based (29) | `tests/audit/test_audit_properties.py` | (Hypothesis-backed) |
| Reproducibility (21) | `tests/audit/test_audit_reproducibility.py` | 3 |
| Provenance (22) | `tests/audit/test_audit_provenance.py` | 6 |
| Security/privacy (30) | `tests/audit/test_audit_security.py` | 10 |
| Performance (24) | `scripts/audit_performance.py` (standalone measurement, not pytest) | -- |
| Long-run stability (25) | `tests/audit/test_audit_long_run_stability.py` | 3 |

**349 backend audit tests total** (`tests/audit/`), **18 frontend audit tests** (`frontend/src/test/{medicalLanguage,domainComputationGuard,confidenceSafetyStates,integration}.test.{ts,tsx}` -- integration.test.tsx predates this phase). All pass.

## 4. Database audit (1)

**Result: PASS, with one documented latent gap.**

- Alembic migration chain reproduces the full ORM schema on a fresh SQLite DB, and is reproducible across two independent fresh databases (`test_audit_db_integrity.py`).
- Deleting a participant cascades correctly across every FK-owned table (`test_deleting_a_participant_cascades_across_all_owned_tables`).
- A forced failure at the final write step leaves no partial row in any table (`test_forced_failure_at_final_write_step_leaves_no_partial_row_in_any_table`) -- transaction rollback via `app.database.engine.session_scope` is sound.
- Two naive double-calls (simulating a race) and a forced double `force_rerun` never leave more than one `is_latest=True` row.
- **Documented gap (not fixed):** there is no database-level partial-unique-index or CHECK constraint enforcing "at most one `is_latest=True` row per (participant_id, target_date)" on `circadian_labels`. The invariant currently holds only through application discipline (`supersede_existing_label` always flips existing rows first) combined with SQLite's single-writer serialization. A concurrent write path on a multi-writer backend (e.g. PostgreSQL under real concurrency) could violate it. **Recommended follow-up** (not performed here, since it's a schema decision beyond a minimal compatibility fix): add a partial unique index `WHERE is_latest = true`.

**Defect found and fixed (cross-cutting with audit 23):** `migrations/env.py`'s `fileConfig(config.config_file_name)` call ran with its default `disable_existing_loggers=True`. Since `scripts/init_db.py` runs `alembic upgrade head` **in-process** (not via a subprocess), this silently and *permanently* disabled every application logger already created in that process (discovered because it broke `app.pipeline.orchestrator`'s error logging for the rest of a pytest session once a migration test ran ahead of a failure-injection test). Fixed: `fileConfig(config.config_file_name, disable_existing_loggers=False)`. Regression test: `test_alembic_upgrade_head_in_process_does_not_disable_application_loggers`.

## 5. Dataset audit (2)

**Result: PASS.** `tests/audit/test_audit_dataset_integrity.py` (13 tests) verified against a real generated synthetic population: row count matches participants x days exactly; window count matches the expected per-participant windowing arithmetic; no duplicated participant/date rows; every participant has exactly the expected contiguous date range (no gaps); no rows beyond the generation window; chronotype and personality-key values are within their valid enumerated sets; MEQ scores are within the instrument's valid range; every clock-hour field is within [0, 24); sleep duration and every duration-minutes field is physically plausible (non-negative, <= 24h); every observation references a valid participant.

## 6. Leakage audit (3, 4)

**Result: PASS -- no leakage bug found in either.**

- **Temporal (3):** an impossible 300-minute screen duration and a distinctive clock time were injected directly into the target day's and target-day+1's DB rows for a real participant; `build_features()` was proven (not assumed) to reflect neither value in any of the 68 output features. The feature builder has a runtime assertion (`app/features/builder.py:177-181`) that `max(day_dates) == target_date - 1`, and `app/pipeline/read.py` independently raises `ValueError` if any returned observation is `>= target_date` -- defense in depth, both layers exercised against real data.
- **Participant (4):** re-derived the actual train/test split and every GroupKFold fold directly from `app.models.splitting`/`app.models.training` (not hardcoded lists) against a real 40-participant dataset; all disjoint. No global `.fit()`/scaler/imputer found anywhere in `app/features`/`app/models` (XGBoost needs none, confirmed by grep and by the codebase's own docstring).

## 7. Circular-time audit (6)

**Result: PASS.** `app.synthetic.time_utils` confirmed as the sole circular-time implementation imported across every clock-math module (alignment, contributors, effectiveness, features, fusion, models, personalization, recommendations, state, synthetic) -- no module reimplements its own wraparound math. All four boundary pairs from the brief (23:50/00:10, 23:59/00:01, 00:00/23:59, 01:00/23:00) compute correctly. End-to-end integration tests fed midnight-crossing values through `compute_phase_alignment`, `detect_anomaly_circular`, `circular_weighted_fusion`, and `compute_graduated_target` and confirmed sane (small-gap, not near-12h) outputs in every case.

**Defect found and fixed (via the state/fusion/alignment audit workstream):** `app/state/behavioral_effect.py`'s `last_meal_tier` classified a `last_meal_hour` clock value against ascending thresholds with **no wraparound handling**. A post-midnight last meal (e.g. 00:30 -- common for misaligned/night-owl synthetic profiles) was misclassified as `"before_8pm"` (best tier, score 100) instead of `"after_11pm"` (worst tier, score 10) -- a full inversion, affecting both the state engine's late-meal amplifier and `app.alignment.behavioral_components.compute_meal_timing_score`. Fixed by applying the same +24h wraparound shift already used elsewhere in the codebase (`app/synthetic/diagnostics.py:_shift_late_night`). No pre-existing test covered this function.

## 8. ML validation

Covered by Phase 5's existing suite (`tests/test_models_*.py`, unchanged) plus this phase's participant-leakage re-verification (§6) and feature-contract audit (§9 below). No new ML-training defect found.

## 9. Feature contract (5)

**Result: PASS.** Exactly 68 features, confirmed both via the manifest's own import-time assertion and by comparing against `build_features()`'s real output (exact order, not just set equality). No target-leakage feature (no feature name contains "dlmo"; no sin/cos pair equals the encoded target). Circular sin/cos encoding verified against the exact formula at every boundary hour. Deterministic ordering confirmed (`FEATURE_NAMES`-driven, not dict-iteration order). **Executable proof** that the validator rejects forbidden features: a real `FeatureVector` was mutated via `dataclasses.replace()` to inject a raw `sleep_onset_hour_raw` feature and, separately, a `resting_hr_mean` physiology feature; `app.features.validation.validate_feature_vector()` correctly failed both (`no_direct_sleep_onset_feature`, `physiology_absent_from_v1`), with a negative control confirming a genuine vector passes.

## 10. State-engine audit (7)

**Result: PASS.** 30/90/180-day trajectories run through the real `app.state.engine`. Constants found: `adapted_max_offset_hours=2.0`, `current_max_offset_hours=3.0` (`app/state/config.py:49,57`), `daily_continuity_cap_minutes=60.0` (`:74`), `adaptation_rate=0.01` (`:43`), `intrinsic_recovery_rate=0.005` (`:46`), `current_pull_rate=0.5` (`:54`) -- all match `docs/state_engine.md`. Intrinsic-DLMO immutability, bound compliance, continuity-cap compliance, directional response to a constructed disturbance, post-disturbance recovery, and (over 180 days) no NaN/Inf/runaway drift/growing oscillation all confirmed.

## 11. DLMO fusion audit (8)

**Result: PASS.** Constants: base weights by confidence tier HIGH 0.65/0.35, MODERATE 0.55/0.45, LOW 0.40/0.60, VERY_LOW 0.20/0.80 (`app/fusion/config.py:64-68`); disagreement thresholds 20/45/75 min (`:72`); continuity caps 60/45/30/20 min by regime (`:85-92`); confidence penalties 0/-8/-18/-30 (`:99-106`). Fusion weights stay simplex-valid across every tier x disagreement-regime combination; circular fusion is correct across midnight; continuity cap holds under extreme disagreement; confidence is monotonically non-increasing in disagreement. All four availability combinations (XGB+state, state-only, XGB-only, neither) behave as documented -- critically, both-unavailable returns `prediction_made=False`/`NO_PREDICTION`, never a fabricated fused value.

## 12. Alignment audit (9)

**Result: PASS.** Locked weights confirmed exactly: 60% phase / 40% behavioral overall (`app/alignment/config.py:30-31`), 25/25/20/15/15 behavioral sub-weights (sleep consistency / morning light / screen / meals / social jetlag, `:34-38`) -- matches `docs/alignment_engine.md` line-for-line. All outputs bounded [0,100] under 17 adversarial input cases. Phase score is monotonically non-increasing with deviation. Phase score depends only on DLMO-derived deviation, not raw sleep-clock time (two chronotypes with identical *relative* deviation score identically). Midnight-crossing cases compute a small circular deviation and a correspondingly high score, not a near-24h naive difference.

## 13. Contributor audit (10)

**Result: PASS.** 60/40 phase-effect/alignment-deficit weights confirmed (`app/contributors/config.py:19-20`). Exactly five core signals; top-3 ordering by composite score, deterministic on ties; no fabricated exercise contributor. `today_anomaly` is computed and surfaced separately from the 6-day historical ranking at the backend layer (not just the Phase 16 UI display-layer truncation) -- an adversarial single-day-anomaly-with-stable-history case confirmed the historical ranking does not silently shift because of one unusual day.

## 14. Recommendation audit (11)

**Result: PASS.** Exactly one primary + at most two supporting nudges enforced at the backend layer (`app/recommendations/`), independent of the Phase 16 UI's own `.slice(0,2)` safety net. Graduated-target fraction confirmed at 0.50 (`app/recommendations/config.py:62`); a midnight-crossing graduated target computes via circular arithmetic and lands on a sane clock time; boundary/impossible-target construction clamps sanely. No medical language found in the recommendation catalogue (cross-checked against the Audit 18 blocklist).

## 15. Intervention-effectiveness audit (12)

**Result: PASS.** A missing observation is excluded from the compliance denominator (not counted as non-compliance). Baseline and intervention periods are correctly separated by date range; no future-relative-to-analysis-date data is read. DLMO changes go through circular difference. The three measurement phases (1 observational / 2 matched-observational / 3 regression-controlled) are labeled consistently between backend `measurement_phase` values and the Phase 16 UI's `PHASE_LABELS` mapping.

## 16. Personalization audit (13) -- HIGH PRIORITY

**Result: PASS on the core replay proof, with one documented catalogue-scoping gap.**

The key executable proof (`test_audit_13_personalization_leakage.py`): built two fully independent SQLite databases -- one whose history ends the day before `as_of_date` ("short"), one with the identical history plus 14 additional days of distinguishable future data ("long") -- and called `update_personalization_state(..., as_of_date=day 20)` against both. The resulting `personal_effect_model.slope`, `num_observations`, and `personalization_phase` are identical regardless of whether future rows exist in the database. All of the actual participant-data read paths (`load_episodes`, `load_intervention_records`, `historical_compliance_values` in `app/effectiveness/db_adapter.py` and `app/personalization/db_adapter.py`) are correctly `as_of_date`-scoped (`log_date < as_of_date`).

**Documented gap (not fixed):** `app.personalization.db_adapter.latest_recommendation_id_for_type` selects the catalogue's currently-`is_active=True` recommendation row **without any `as_of_date` scoping**. If the recommendation catalogue itself were ever edited mid-study (a row deactivated/replaced after `as_of_date`), a replay of "what would have been decided on day t" could pick a different `recommendation_id` than what was actually active on day t. This is a catalogue-versioning gap, not a participant-behavioral-data leak -- the catalogue is static reference data seeded once in the current deployment pattern, not participant-specific history, and the function's own docstring already flags the single-active-row assumption. Recommended follow-up: an `effective_date`/`superseded_date` pair on `Recommendation` if the catalogue is ever made editable during a live study.

## 17. Safety audit (16, 17)

**Result: PASS on both.**

- **Confidence (16):** exact boundary comparisons confirmed (`>=80` HIGH, `>=60` MODERATE, `>=40` LOW, else NO_PREDICTION, `app/fusion/confidence.py:57-63`), tested at all six boundary values including the `.999` cases. Completeness threshold is exactly 0.5 (`app/fusion/config.py:112`), confidence threshold exactly 40.0. All three no-prediction triggers (critical data missing, <50% completeness, confidence <40) isolated and confirmed independent. `approximate` propagates end to end from the fusion engine through `StatusResponse`.
- **Safety patterns (17):** all four flag types (`persistent_late_phase`, `persistent_early_phase`, `continuous_dlmo_drift`, `low_alignment_despite_compliance`, `app/safety/enums.py:17-22`) tested with both normal and pathological trajectories. **Critical adversarial case:** 12 nights alternating 23:50/00:10 sleep onset did **not** false-trigger a drift flag -- confirms `unwrap_circular_series`/`compute_circular_trend_minutes_per_day` correctly handle wraparound. Minimum-observation floor confirmed exactly at 10. Flag lifecycle (PERSISTING/RESOLVED) confirmed via `reconcile_flag()`.

## 18. Cold start & bandit safety audit (14, 15)

**Result: PASS.** A fresh participant starts at "literature" personalization with no history; progression through personal_ranking -> personal_effect -> adaptive_policy occurs at the documented thresholds (`app/personalization/config.py`: 3 obs/3 weeks -> ranking, 14 obs/6 weeks -> effect model, 42 obs/12 weeks -> adaptive). Each intervention type progresses independently (confirmed with per-type history construction). Bandit action space is structurally constrained to the safe catalogue; posterior state persists to the DB between calls; **bandit sampling requires an explicit caller-supplied RNG** (confirmed via `test_personalization_bandit_sampling_requires_an_explicit_caller_supplied_rng`), closing the reproducibility concern this audit was specifically watching for.

## 19. API contract audit (19)

**Result: PASS, with one real defect found and fixed.**

Input validation, response-schema exactness (field-by-field, no extra keys), safety-suppression propagation, no-raw-DB-object leakage, no side effects on GET, and idempotency all verified with executable tests against a real `TestClient`.

**Defect found and fixed:** any generic (non-`ValueError`) pipeline failure -- e.g. a real `SQLAlchemyError` during the write transaction -- had its raw `str(exc)` forwarded verbatim into the client-facing `detail` field of the 503 response, violating the documented "no stack trace or database detail is ever leaked" contract (`docs/api_architecture.md` §8). Fixed in `app/api/services/inference_service.py`: non-client-correctable failure stages now return `detail=f"stage={result.failure_stage}"` only; the full message is logged server-side. Regression tests: `test_unexpected_exception_surfaces_as_500_without_leaking_traceback`, `test_inference_mid_transaction_failure_rolls_back_fully`.

**Second, related defect found during audit synthesis (cross-cutting with §22 below) and fixed:** broadening the pipeline's `read` stage to catch generic exceptions (see §22) meant a raw DB-layer error during read would flow through the *client-safe* `"read"`/`NotFoundError(detail=result.failure_message)` path -- reopening the exact leak the first fix closed. Fixed by splitting the failure stage into `"read"` (deliberately-authored `ValueError`s from `app/pipeline/read.py`, safe to forward) and `"read_infrastructure"` (anything else, routed to the generic safe 503). Regression test: `test_db_layer_read_failure_surfaces_as_503_without_leaking_raw_message`.

## 20. UI/API contract audit (20)

**Result: PASS.** Field-by-field diff of every Pydantic schema (`app/api/schemas/*.py`) against `frontend/src/api/types.ts`: no drift. A grep-based "domain computation guard" test (`frontend/src/test/domainComputationGuard.test.ts`) scans every dashboard component for arithmetic near domain-sounding terms (dlmo, alignment, confidence, contributor, severity, safety, recommendation, compliance) after stripping strings/comments/imports; every genuine hit reviewed and confirmed benign (formatting an already-final API value, or SVG pixel geometry -- never deriving a new domain score). All 8 required UI states (normal, high/moderate/low confidence, no-prediction, safety moderate/high, history, intervention feedback) verified rendering correctly against schema-shaped mocked responses.

## 21. Reproducibility (21)

**Result: PASS.** Two full pipeline runs off an identical DB snapshot (same seed, same feature/model/config versions) match on every component: XGBoost prediction, state prediction, fused DLMO, alignment, contributors, recommendation. The committed database rows from both runs are identical. Bandit/personalization sampling was confirmed to require an explicit caller-supplied RNG rather than unseeded global randomness (see §18), which is what makes the reproducibility guarantee actually hold for the adaptive-policy phase, not just the deterministic phases.

## 22. Version provenance (22)

**Result: PARTIAL -- documented, not fixed.** `CircadianLabel.training_run_id -> TrainingRun.model_version` gives structured, queryable provenance for the XGBoost model version on the headline result row. However:

- `CircadianLabel` itself has no columns for pipeline/fusion/state/alignment/recommendation config version.
- `AlignmentResult.component_snapshot['provenance']` **does** carry pipeline/feature/state/fusion/alignment/contributor/recommendation config versions -- but only inside an opaque, unindexed JSON blob, not structured/queryable columns.
- `ContributorResult` and `InterventionLog` have **no version column of any kind** -- not even inside a JSON blob.

**Why not fixed here:** unlike the Phase 16 "minimal compatibility fix" pattern (adding a couple of nullable columns to expose an already-computed value), full structured provenance would mean adding version columns across three-plus tables and deciding a schema for it -- a deliberate design decision, not a bug fix. Documented as a release-blocking-for-strict-provenance-guarantees gap; see §29.

## 23. Failure injection (23)

**Result: PASS, with two real defects found and fixed.** Deliberately injected failures at every stage (DB/read, XGBoost, feature generation, state engine, fusion, alignment, recommendation, persistence). XGBoost/feature/alignment/recommendation/persistence failures already degraded correctly (graceful state-only fallback for XGBoost; `FAILED` + nothing written for the rest).

**Defects found and fixed:** `run_state_step` and `fuse()` were called **outside any try/except** in `app/pipeline/orchestrator.py` -- unlike every other stage. A state-engine or fusion exception would crash `run_daily_inference` entirely rather than degrade to a reported `FAILED` result. Fixed: wrapped both in try/except mirroring the existing pattern, returning `_fail(..., "state_engine"/"fusion", ...)`. The read stage's `except ValueError` was also broadened to `except Exception` so a DB-layer error degrades rather than crashes (see §19 for the client-facing-leak consequence this created and the follow-up fix). **Mitigating factor:** the API layer's blanket exception handler already converted any unhandled pipeline crash into a safe generic 500 before this fix, so no client was ever exposed to it -- but the gap was real for any non-API caller of `run_daily_inference` and inconsistent with the documented per-stage failure contract.

## 24. Performance (24)

**Result: measured, no optimization performed (as instructed).** `scripts/audit_performance.py`, run for n=1/10/100 participants against the real pipeline:

| Stage | n=1 mean | n=10 mean | n=100 mean |
|---|---|---|---|
| feature_generation | 1.94ms | 1.19ms | 1.08ms |
| xgboost_inference | 54.10ms | 10.93ms | 13.10ms |
| state_computation | 0.04ms | 0.03ms | 0.04ms |
| fusion | 0.06ms | 0.04ms | 0.05ms |
| alignment | 0.11ms | 0.09ms | 0.09ms |
| contributor_ranking | 0.21ms | 0.18ms | 0.17ms |
| recommendation_selection | 4.60ms | 1.84ms | 1.73ms |
| **run_daily_inference (total)** | 49.51ms | 40.08ms (median 22.79ms) | 29.20ms (median 23.58ms) |

`GET /participants/{id}` API response: 2.17ms. **Observation (not a fix):** XGBoost inference dominates (77-89% of summed stage time in every n); the n=1 case's higher mean is model-load warmup, not a per-call cost (median drops sharply once warm). No other obvious bottleneck (no O(n^2) pattern) observed at this scale.

## 25. Long-run stability (25)

**Result: PASS.** 180-day simulations for three constructed profiles (well-aligned, chronically misaligned, improving-via-intervention at day 60) through the real state -> fusion -> alignment pipeline day by day: no NaN/Inf, no out-of-bound drift, no growing-amplitude oscillation. The well-aligned profile settled to a high mean score; the improving profile showed a genuine post-intervention score increase (not a stuck/pinned value); the misaligned profile stayed within documented state bounds throughout.

## 26. Scientific-assumption inventory

| Constant | Value | File:Line | Class | Basis |
|---|---|---|---|---|
| Adapted-DLMO bound | ±2.0h | `app/state/config.py:49` | B | Project modeling assumption |
| Current-DLMO bound | ±3.0h | `app/state/config.py:57` | B | Project modeling assumption |
| Daily state continuity cap | 60 min | `app/state/config.py:74` | C | Engineering implementation choice |
| Adaptation rate | 0.01/day | `app/state/config.py:43` | B | Project modeling assumption |
| Intrinsic recovery rate | 0.005/day | `app/state/config.py:46` | B | Project modeling assumption |
| Current-DLMO pull rate | 0.5 | `app/state/config.py:54` | C | Engineering implementation choice |
| Fusion weights by confidence tier | 0.65/0.35 .. 0.20/0.80 | `app/fusion/config.py:64-68` | B | Project modeling assumption |
| Disagreement thresholds | 20/45/75 min | `app/fusion/config.py:72` | C | Engineering implementation choice |
| Fusion continuity caps by regime | 60/45/30/20 min | `app/fusion/config.py:85-92` | C | Engineering implementation choice |
| Confidence penalties by disagreement regime | 0/-8/-18/-30 | `app/fusion/config.py:99-106` | B | Project modeling assumption |
| Confidence label thresholds | 80/60/40 | `app/fusion/config.py:109` | C | Engineering implementation choice (explicitly documented as such in `app/safety/config.py:3-11`) |
| Data-completeness no-prediction threshold | 0.5 | `app/fusion/config.py:112` | C | Engineering implementation choice |
| Alignment: phase/behavioral split | 60% / 40% | `app/alignment/config.py:30-31` | B | Project modeling assumption |
| Alignment behavioral sub-weights | 25/25/20/15/15 | `app/alignment/config.py:34-38` | B | Project modeling assumption |
| Contributor formula weights | 60% phase effect / 40% alignment deficit | `app/contributors/config.py:19-20` | B | Project modeling assumption |
| Recommendation severity bands | 80/60/40 | `app/recommendations/config.py:29-32` | C | Engineering implementation choice |
| Recommendation severity weight pairs | 0.55/0.45 .. 0.20/0.80 | `app/recommendations/config.py:35-40` | B | Project modeling assumption |
| Graduated target fraction | 0.50 | `app/recommendations/config.py:62` | C | Engineering implementation choice |
| Feasibility weights (compliance/difficulty/failure penalty) | 0.30/0.25/0.20 | `app/recommendations/config.py:74-82` | C | Engineering implementation choice |
| Personalization: ranking threshold | 3 obs / 3 weeks | `app/personalization/config.py:18-19` | C | Explicitly self-documented as "project engineering graduation rule, not literature-backed" (`app/personalization/config.py:3-5`) |
| Personalization: effect-model threshold | 14 obs / 6 weeks | `app/personalization/config.py:22-23` | C | Same as above |
| Personalization: adaptive-policy threshold | 42 obs / 12 weeks | `app/personalization/config.py:26-27` | C | Same as above |
| Personalization blend weights | 0.40 personal / 0.60 literature | `app/personalization/config.py:40-41` | C | Engineering implementation choice |
| Safety: min observations for a flag | 10 | `app/safety/config.py:30` | C | Engineering implementation choice |
| Safety: persistent-late-phase threshold | 2:00 AM | `app/safety/config.py:33` | B | Project modeling assumption, explicitly NOT claimed as a clinical threshold (`app/safety/config.py:11`) |
| Safety: persistent-early-phase threshold | 7:30 PM | `app/safety/config.py:36` | B | Same caveat |
| Safety: drift threshold | 20 min/day | `app/safety/config.py:39` | C | Engineering implementation choice |
| Safety: low-alignment-despite-compliance threshold | 45.0 score / 0.70 compliance | `app/safety/config.py:42-43` | C | Engineering implementation choice |

No constant in the system is classified (A) literature-backed with an actual cited source in-code; several docstrings (`app/personalization/config.py:3-5`, `app/safety/config.py:3-11`) already explicitly self-disclaim literature-validation status, which is the correct posture and was verified, not just trusted.

## 27. Synthetic-data limitations

**Result: PASS, no fix needed.** A repository-wide scan (`docs/`, `README.md`, `app/`) for unscoped accuracy/performance claims (e.g. "N% accuracy" or "N% of participants" without a "synthetic" qualifier) found **zero matches**. `docs/model_training_and_validation.md` already explicitly scopes every metric: *"This model is trained and validated on synthetic data. ... Every metric below reads 'on the synthetic held-out ...'"* -- confirmed this framing is used consistently throughout that document, not just in its header.

## 28. Golden end-to-end fixture

**Result: PASS.** `tests/audit/test_audit_golden_participant.py` (5 tests) drives a deterministic participant through onboarding -> multiple days of behavioral observations -> daily inference -> safety evaluation -> recommendation -> a simulated intervention outcome -> effectiveness evaluation -> personalization update -> a subsequent inference reflecting the updated state, using the real code paths throughout (no mocks), with independently-derived expected alignment/confidence values checked against documented formulas. This file is intended as a standing regression fixture for future phases.

## 29. Security/privacy baseline

**Result: PASS (prototype-level, as scoped).** No `.env` committed (only `.env.example`); `.gitignore` excludes `.env`/database files; no DB credentials anywhere in `frontend/`; no f-string/percent-built raw SQL anywhere in `app/` (ORM-only); no logging call found passing a raw observation/request payload (IDs/aggregates only); every POST endpoint declares a Pydantic request schema; participant-scope boundaries enforced end to end -- participant B cannot read participant A's behavior history via the scoped endpoint, submitting an outcome under the wrong participant ID is rejected, and the history endpoint never returns cross-participant rows (all three verified with a real `TestClient`, not by reading route code).

## 30. Known limitations

1. No DB-level constraint prevents two `is_latest=True` rows for the same participant/date (§4) -- enforced by application discipline only.
2. Version provenance is structured only for the model version; fusion/state/alignment/recommendation config versions live in an opaque JSON blob (alignment only) or nowhere at all (contributors, interventions) (§22).
3. The personalization catalogue lookup (`latest_recommendation_id_for_type`) is not `as_of_date`-scoped -- a latent gap if the recommendation catalogue is ever edited mid-study (§16). Participant behavioral/outcome data itself is correctly scoped throughout.
4. Performance was measured, not load-tested at production scale; XGBoost inference is the dominant cost at every measured scale (§24).

## 31. Unresolved issues

None of the above four limitations block release under the stated criteria (§32) -- all are either latent (require a specific future condition: concurrent multi-writer DB, catalogue edited mid-study) or explicitly out of scope for a "no redesign" audit phase (structured provenance is a schema decision, not a defect). They are release notes for Phase 18, not open defects.

## 32. Final release recommendation

**CONDITIONAL PASS.**

Criteria walkthrough:
- Critical tests pass: **yes** -- 1006/1007 backend (1 skip is an explicitly-gated opt-in test), 60/60 frontend, clean production build.
- No participant leakage: **yes** (§6).
- No temporal leakage: **yes** (§6, §16 -- including the high-priority personalization replay proof).
- No critical safety failure: **yes** (§17, §18 -- medical-language scan clean on both backend and frontend).
- No recommendation medical-boundary violation: **yes** (§14, §18).
- Database transactions are sound: **yes**, with one documented non-critical latent gap (§4, §30.1).
- Core circular arithmetic is correct: **yes**, one real bug found and fixed (§7).
- Reproducibility passes: **yes** (§21).
- API/UI contract works: **yes**, two real leak-adjacent defects found and fixed (§19, §20).

The system meets every PASS-blocking criterion. It is CONDITIONAL rather than a clean PASS solely because of the three non-critical, documented limitations in §30 (no DB-level uniqueness constraint on `is_latest`, incomplete structured version provenance, and the catalogue as_of_date-scoping gap) -- each is a real gap worth closing deliberately, none of them caused an observed incorrect output anywhere in this audit, and closing them properly requires a schema/design decision rather than a same-phase bug fix.

## Appendix: defects fixed this phase

| # | Defect | File(s) | Regression test |
|---|---|---|---|
| 1 | `last_meal_tier` had no midnight wraparound -- inverted meal-timing scoring for post-midnight meals | `app/state/behavioral_effect.py` | covered by `test_audit_state_engine.py` / `test_audit_long_run_stability.py` trajectories using post-midnight values |
| 2 | 503 responses forwarded raw internal exception text to clients | `app/api/services/inference_service.py` | `test_unexpected_exception_surfaces_as_500_without_leaking_traceback`, `test_inference_mid_transaction_failure_rolls_back_fully` |
| 3 | `run_state_step`/`fuse()` calls unguarded in the orchestrator -- could crash instead of failing gracefully | `app/pipeline/orchestrator.py` | `test_audit_failure_injection.py` cases 4 and 5 |
| 4 | Read-stage broadening (fix #3's side effect) reopened the exception-leak fix #2 closed, via the "read" stage's client-safe detail-forwarding path | `app/pipeline/orchestrator.py`, `app/api/services/inference_service.py` | `test_db_layer_read_failure_surfaces_as_503_without_leaking_raw_message` |
| 5 | `alembic upgrade head` run in-process permanently disabled application loggers (via `fileConfig`'s default `disable_existing_loggers=True`) | `migrations/env.py` | `test_alembic_upgrade_head_in_process_does_not_disable_application_loggers` |
| 6 | `SyntaxWarning` from an unescaped `\-` in a non-raw docstring | `app/effectiveness/lifecycle.py` | N/A (warning-only, not a test-covered behavior) |

Additional infrastructure fixes made to land this phase cleanly (not defects in application behavior): installed `hypothesis` (already declared in `requirements.txt` for the property-based tests) and `@types/node` (frontend, for the new Node-`fs`-based grep-audit test files), and added `"node"` to `frontend/tsconfig.app.json`'s `types` array so `npm run build` type-checks the new test files.

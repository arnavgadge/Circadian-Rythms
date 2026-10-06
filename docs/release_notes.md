# Release Notes — v1.0.0-research-demo (2026-09-09)

CircadianIQ is a research/demo system that computationally estimates
circadian phase (DLMO) from behavioral and environmental proxies,
evaluates alignment, and drives personalized, safety-gated behavioral
recommendations. This is a **research demo release**, not a clinical
product — see "Scientific caveats" below.

For the authoritative, machine-readable component-version freeze, see
`release/version_manifest.json`. Phase 18 release status: see that
file (this document summarizes it in prose but does not itself issue
the final verdict).

## Major capabilities

- **DLMO estimation** — an XGBoost sin/cos circular-regression model
  trained on engineered behavioral features (`app/models/`, `app/features/`).
- **Mechanistic state-model estimation** — an independent, non-ML
  circadian state model, fused with the ML estimate (`app/state/`, `app/fusion/`).
- **Alignment scoring** — quantifies how well actual behavior aligns
  with the estimated circadian phase (`app/alignment/`).
- **Contributor identification** — ranks the behavioral/environmental
  factors driving misalignment (`app/contributors/`).
- **Recommendation engine** — selects and scores candidate
  interventions from a catalogue against relevance, feasibility, and
  targeting criteria (`app/recommendations/`).
- **Intervention effectiveness evaluation** — measures whether
  delivered interventions produced measurable outcome change (`app/effectiveness/`).
- **Personalization** — learns per-participant intervention-effect
  models from accumulated evidence and adapts targeting/ranking over
  time (`app/personalization/`).
- **Safety layer** — the single authoritative confidence-gate,
  pattern-detection, and suppression layer applied before any output
  reaches a client (`app/safety/`).
- **API** — FastAPI backend serving all of the above (`app/api/`).
- **Dashboard UI** — React/TypeScript participant dashboard visualizing
  estimated phase, alignment, contributors, recommendations, and
  safety state (`frontend/`).

## Validated metrics

From the frozen Phase 5 training run
(`models/model_metadata_v1.json`, `release/results/`):

**93.73% of held-out synthetic test windows were within ±60 minutes**
(MAE 24.47 min).

This is accuracy against a synthetic ground truth on a
subject-held-out split, measured within this project's own simulated
population. It is **not** a claim of human or clinical accuracy — see
"Scientific caveats" below. Full metrics, baseline comparisons, and
diagnostic plots are in `release/results/*.csv` (model_metrics,
baseline_comparison, chronotype_metrics, personality_metrics,
feature_importance, shap_importance, cv_per_fold, test_summary) and
`release/figures/*.png`, both taken directly from the original
validated training run without regeneration.

## Tests

As of Phase 17 completion: **1006 backend tests passed, 1 skipped
(explicitly gated opt-in test), 0 failed**, plus **60/60 frontend
tests**, plus a clean production build. Phase 18 packaging work
extended this baseline; the full suite was re-verified after all
Phase 18 packaging landed — see the Phase 18 final test run recorded
alongside this release (orchestrating-session regression pass) rather
than a count restated here.

## Known limitations

1. **No DB-level uniqueness constraint on `circadian_labels.is_latest`.**
   Enforced by application discipline only. A partial unique index
   would close this at the schema level; it has not been added. See
   `app/database/models/circadian.py`.

2. **Structured version-provenance columns are incomplete.** Only the
   XGBoost model version is a queryable column
   (`CircadianLabel.training_run_id -> TrainingRun.model_version`).
   Pipeline/fusion/state/alignment/recommendation config versions
   exist only inside the opaque `AlignmentResult.component_snapshot`
   JSON blob. `ContributorResult` and `InterventionLog` carry no
   version information at all.

3. **`app.personalization.db_adapter.latest_recommendation_id_for_type`
   is not `as_of_date`-scoped** — a catalogue-versioning gap, **not**
   a participant-data leak. Participant behavioral/outcome data is
   correctly `as_of_date`-scoped everywhere, verified by an explicit
   temporal-replay proof in Phase 17.

These three limitations are carried forward unresolved into this
release and are documented, not hidden — see `docs/developer_handoff.md`
for exact file pointers and `release/version_manifest.json` for the
release-level record.

## Scientific caveats

- **Synthetic data only.** All training, validation, and demo data in
  this release are produced by this project's own synthetic simulator
  (`app/synthetic/`). No real human physiological or behavioral data
  has been used at any point.
- **No clinical validation.** CircadianIQ computationally *estimates*
  circadian phase; it does not measure laboratory DLMO and must never
  be presented as a clinical measurement, diagnosis, or treatment.
- **Project-modeling-assumption weights.** The synthetic generator's
  behavioral-personality distributions, the state model's parameters,
  and the fusion/alignment weighting are project design choices, not
  values fit to or validated against real epidemiological or clinical
  data. See `docs/scientific_assumptions.md` for the full accounting
  of these assumptions and `docs/research_handoff.md` for what would
  be required to validate them against real-world data.

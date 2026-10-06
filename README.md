# CircadianIQ

**Release `v1.0.0-research-demo`** — a frozen research/demo release.
Phase 17 (system-wide adversarial audit): **CONDITIONAL PASS**. Phase 18
(freeze/reproducibility/documentation): see
`release/version_manifest.json`. Read
`docs/CircadianIQ_Final_Master_Specification.md` for the single
consolidated technical specification this README summarizes.

CircadianIQ is a circadian-rhythm alignment research system. It
estimates a person's circadian phase (DLMO) from everyday behavioral
and environmental signals, evaluates how well their behavior aligns
with that estimated phase, identifies the behaviors that most affect
misalignment, and offers graduated, safety-bounded behavioral
recommendations, with intervention-outcome feedback and long-term
personalization.

**Team:** Prithviraj Khedekar, Arnav Pranil Gadge
**Institution:** VIT Pune

## 1. Scientific scope and boundary

CircadianIQ **computationally estimates** circadian phase from
behavioral and environmental proxies. It does **not** directly measure
laboratory DLMO, and it must never be presented as a clinical
measurement or diagnosis. **Every metric, weight, and simulated
trajectory in this release was produced on synthetic data — no
component has been validated against real human circadian/DLMO
measurements.** The validated headline ML result must always be stated
as **"93.73% of held-out synthetic test windows were within ±60
minutes"** — never as human or clinical accuracy. See
`docs/scientific_assumptions.md` for a complete, file-cited inventory
of which numerical constants are literature-backed vs. project
modeling assumptions vs. engineering choices (in this release, none
are literature-backed with an actual in-code citation — all are
modeling assumptions or engineering choices, stated as such).

## 2. Architecture

The system is a hybrid SQL + Python + API + UI pipeline:

```
SQL database  <->  Python computational pipeline  <->  FastAPI (/api/v1)  <->  React/TypeScript dashboard
```

SQL is the **authoritative source of truth** for historical behavioral
records, prediction outputs, current participant state, intervention
history, compliance history, and learned personalization state — never
bypassed. Python owns all computation: feature engineering, ML
inference, circadian state-model computation, DLMO fusion, alignment
calculation, contributor ranking, recommendation selection,
personalization logic, and safety logic. FastAPI exposes exactly this
computation over HTTP with no domain logic of its own; the React UI
consumes the API exclusively and computes nothing domain-specific
itself (verified adversarially in Phase 17 audit 20).

The daily inference flow:

```
READ FROM SQL
    -> feature engineering
    -> XGBoost prediction
    -> state-model prediction
    -> DLMO fusion
    -> alignment
    -> contributors
    -> recommendation
    -> WRITE TO SQL (atomically, one transaction)
```

Training is a separate, offline process; personalization updates run
as a separate, `as_of_date`-scoped offline process that daily inference
only ever reads from. See `docs/CircadianIQ_Final_Master_Specification.md`
for the full per-component breakdown, `docs/architecture_diagrams.md`
for 7 Mermaid diagrams (system, ER, sequence, ML pipeline, feedback
loop, personalization progression, safety decision tree), and
`docs/final_database_design.md` / `docs/architecture.md` for the
detailed schema/architecture writeups.

## 3. Repository layout

```
app/
    config/           Environment-driven application configuration (AppConfig)
    database/         DB abstraction: Phase 1 raw-SQL primitives + Phase 2 SQLAlchemy ORM
        models/       SQLAlchemy ORM models for the full relational schema
    synthetic/        Phase 3 synthetic population + 30-day longitudinal data generator
    features/         Phase 4 feature engineering: 6-day window -> 68-feature vector
    models/           Phase 5 XGBoost training + validation pipeline (app/database/models/ is the DB schema, above)
    scripts/          Runnable app-level scripts (python -m app.scripts.<name>)
    state/            Phase 6 state engine: intrinsic -> adapted -> current DLMO
    fusion/           Phase 7 DLMO fusion: XGBoost + state engine -> fused DLMO
    alignment/        Phase 8 alignment engine: fused DLMO + behavior -> 0-100 score
    contributors/     Phase 9 contributor ranking: top 3 behavioral contributors to misalignment
    recommendations/  Phase 10 recommendation engine: 1 primary intervention + 2 supporting nudges
    pipeline/         Phase 11 daily inference orchestration: DB -> features -> XGBoost+state -> fusion -> alignment -> contributors -> recommendation -> DB
    effectiveness/    Phase 12 intervention feedback: compliance + observational/matched/regression effect estimation
    personalization/  Phase 13 long-term personalization: ranking -> personal effect model -> contextual bandit
    safety/           Phase 14 safety + confidence layer: confidence gating, unusual-pattern detection, safe output
    api/              Phase 15 application/API layer: FastAPI routes -> services -> domain modules -> repositories -> DB
    logging_config.py Central logging setup (stdlib logging, no print())
    health.py         Startup health check (config, directories, DB abstraction)

data/
    raw/              Raw input data (git-ignored)
    synthetic/        Synthetic dataset exports + diagnostics (git-ignored)
    processed/        Processed/feature-ready data (git-ignored)

migrations/           Alembic migration environment + versioned schema revisions
models/               Serialized trained model artifacts (git-ignored except the frozen v1.1 release artifact)
scripts/              Standalone operational scripts (environment check, DB init, checksums, performance audit)
tests/                Pytest suite (tests/audit/ = Phase 17 system-wide audit tests)
notebooks/            Exploratory notebooks
docs/                 Architecture, design, methodology, and release documentation (docs/paper/ = IEEE-style draft; docs/architecture_diagrams.md = Mermaid diagrams)
release/              Phase 18 frozen release artifacts: version_manifest.json, reproducibility_manifest.json, results/*.csv, figures/*.png, demo/demo_scenarios.json, checksums.sha256
frontend/             React + TypeScript dashboard (Phase 16) -- see docs/ui_architecture.md
```

## 4. Prerequisites

- Python 3.11+ (developed/tested on 3.14.3).
- Node.js 18+ / npm (developed/tested on Node v24.14.0 / npm 11.9.0) -- only needed for the frontend.
- SQLite (bundled with Python) for local development and the demo; PostgreSQL is scaffolded (`app/database/connection.py`) but not exercised by this release.
- No GPU required; XGBoost training runs on CPU in seconds-to-minutes at the synthetic dataset's scale.

## 5. Configuration

Configuration is centralized in `app/config/settings.py` as an
immutable `AppConfig` dataclass, built by `load_config()` from
environment variables (with defaults for local development). Copy
`.env.example` to `.env` and adjust as needed; `python-dotenv` loads
it automatically if present.

Key variables: `CIRCADIANIQ_ENV`, `CIRCADIANIQ_DATABASE_URL`,
`CIRCADIANIQ_DATA_DIR` (and per-subdirectory overrides),
`CIRCADIANIQ_MODEL_DIR`, `CIRCADIANIQ_LOG_LEVEL`.

Two layers coexist in `app/database/`: Phase 1 raw-SQL primitives
(`connection.py`/`transaction.py`) and the Phase 2 SQLAlchemy ORM layer
(`engine.py`/`models/`/`init_db.py`/`seed.py`), the primary interface
used throughout. Schema changes go through Alembic (`alembic.ini`,
`migrations/`) so existing data survives a migration. See
`docs/final_database_design.md` for the final, consolidated schema
design (supersedes the original `docs/database_architecture.md` for
anything added in Phases 14-16).

## 6. Installation

```bash
python -m venv .venv
# source .venv/bin/activate   (or .venv\Scripts\activate on Windows)
pip install -r requirements.txt          # floor-version dev install
# -- or, for exact release reproduction --
pip install -r requirements-lock.txt     # pinned to this release's exact versions
```

## 7. Environment setup

```bash
cp .env.example .env
python scripts/check_environment.py
```

Key variables (see §5 above): `CIRCADIANIQ_ENV`,
`CIRCADIANIQ_DATABASE_URL`, `CIRCADIANIQ_DATA_DIR`,
`CIRCADIANIQ_MODEL_DIR`, `CIRCADIANIQ_LOG_LEVEL`.

## 8. Database initialization

```bash
python scripts/init_db.py
```

Runs `alembic upgrade head` (current head: `e5f9c27b4d8a`) and seeds
the reference recommendation catalogue.

## 9. Synthetic data generation

```bash
python -m app.scripts.generate_synthetic_data --participants 1000 --days 30 --seed 42
```

Generates a seeded, fully reproducible synthetic population (see
`docs/synthetic_data_generation.md`, `docs/scientific_assumptions.md`
for which generation parameters are project assumptions vs. engineering
choices). Pass `--reset` to wipe existing participants first (never the
default).

## 10. Model training

```bash
python -m app.scripts.build_feature_dataset
python -m app.scripts.train_model
```

Trains two XGBoost models (sin/cos of the circular DLMO target) on a
participant-level held-out split, writes versioned artifacts to
`models/` (**never overwrites a prior version**), and logs a
`training_runs` row. This release ships a **frozen** model artifact
(`models/xgboost_dlmo_{sin,cos}_v1.pkl`, version "v1.1") — running this
again creates a new version, it does not replace the frozen one. See
`docs/final_ml_methodology.md`.

## 11. Validation

`train_model.py` also runs the full held-out-test + 5-fold-CV
validation and writes diagnostic plots. The **validated, frozen
result** for this release: **93.73% of held-out synthetic test windows
were within ±60 minutes** (MAE 24.47 min). Full numbers:
`release/results/model_metrics.csv`; figures: `release/figures/*.png`;
Phase 17's full 30-category system-wide adversarial audit (not just the
ML model): `docs/system_validation_and_audit.md`. Run just the audit
suite: `pytest tests/audit/`. A standalone, non-pytest performance
measurement: `python -m scripts.audit_performance` (measurement only,
no optimization).

## 12. Backend startup

```bash
uvicorn app.api.main:app --reload
```

Interactive OpenAPI docs: http://127.0.0.1:8000/docs (raw schema at
`/openapi.json`). Every route is versioned under `/api/v1`. See
`docs/api_architecture.md` for the full endpoint catalogue and
**prototype security limitations** -- this API has no authentication
and is a local-development tool, not a production-secured service.

## 13. Frontend startup

The dashboard (`frontend/`) is a separate Vite/React app that talks
to the API above over HTTP -- it needs the API running first.

```bash
cd frontend
npm install
cp .env.example .env   # VITE_API_BASE_URL defaults to http://127.0.0.1:8000/api/v1
npm run dev
```

Dashboard: http://127.0.0.1:5173. `npm test` runs the frontend test
suite (Vitest); `npm run build` produces a production build. See
`docs/ui_architecture.md` for the full UI architecture writeup.

## 14. Demo instructions

```bash
python -m app.scripts.seed_demo_scenarios --reset
```

Seeds a **dedicated demo database** (`data/demo.db`, never the real dev
DB) with 4 deterministic scenario participants, selected by actually
running the real pipeline (not fabricated): `1` = NORMAL, `3` =
LOW_CONFIDENCE, `25` = MODERATE_SAFETY_FLAG, `41` = HIGH_SAFETY_FLAG
(recommendation suppressed). See `release/demo/demo_scenarios.json` for
the full disclosure of how each was selected/constructed, and
`docs/demo_runbook.md` for a full 5-10 minute guided walkthrough
(introduction -> onboarding -> inference -> clock/alignment/
contributors/recommendation -> history -> intervention feedback ->
personalization -> safety boundary -> DBMS queries -> ML results).
To view: set `CIRCADIANIQ_DATABASE_URL=sqlite:///<path>/data/demo.db`
before starting the API, then visit `/dashboard/1`, `/dashboard/25`,
etc. in the frontend. Live SQL queries against the demo data:
`docs/dbms_demo_queries.sql`.

## 15. Reproduction procedure

```bash
python -m app.scripts.reproduce_release
```

One command, seed-deterministic, against a **disposable** database
(`data/release_reproduction.db` by default -- never the real dev DB
unless you explicitly pass `--db-name circadianiq --reset`). Runs
schema init, synthetic generation, feature building, diagnostics, and a
few real inference calls; writes `release/reproducibility_manifest.json`.
Pass `--retrain` to also retrain (creates a new model version, never
overwrites the frozen `v1.1` artifact); `--participants`/`--days`/
`--seed` to control scale. Full details, including what is and isn't
guaranteed to be bit-identical to the original training run:
`docs/reproducibility.md`.

## 16. Testing

```bash
pytest                          # full backend suite (unit + integration + Phase 17 audit tests)
pytest tests/audit/             # just the Phase 17 system-wide audit suite
cd frontend && npm test         # frontend suite (Vitest)
cd frontend && npm run build    # production build / type-check
```

See `docs/system_validation_and_audit.md` for the full Phase 17 audit
report and `docs/release_notes.md` for this release's final test run
totals.

## 17. Final results

**Held-out synthetic test (frozen, do not recompute or alter):**
93.73% of held-out synthetic test windows were within ±60 minutes; MAE
24.47 min; RMSE 31.86 min; median absolute error 19.71 min; bias -0.82
min (n=4800 windows / 200 held-out participants). 5-fold CV: MAE 25.22
± 1.20 min; within ±60min 93.03% ± 0.74%. Baselines: participant-mean
57.2 min MAE / 67.6% within ±60min; MSFsc-proxy 342.1 min MAE / 0.0%
within ±60min. Machine-readable: `release/results/*.csv`. Figures:
`release/figures/*.png`. Full methodology: `docs/final_ml_methodology.md`.
**This describes synthetic-benchmark performance only.**

Full Phase 17 system-wide audit (30 categories, not just the ML
model): **CONDITIONAL PASS**, 6 real defects found and fixed with
regression tests, no participant/temporal leakage, no safety/medical-
boundary violation. Full report: `docs/system_validation_and_audit.md`.

## 18. Limitations

**Three known, non-critical limitations** (found in Phase 17, preserved
here, not silently fixed during Phase 18 packaging):
1. No DB-level uniqueness constraint on `circadian_labels.is_latest` (application-discipline-enforced only).
2. Structured version-provenance columns are incomplete (only the XGBoost model version is a queryable column).
3. `latest_recommendation_id_for_type` (personalization catalogue lookup) is not `as_of_date`-scoped -- a catalogue-versioning gap, **not** a participant-data leak.

Plus: synthetic-data-only validation everywhere in this release; the
`feature_manifest_version` label inconsistency between the trained
model's own metadata ("phase4-v1") and the current code constant
("1.0.0") -- a naming mismatch, not a feature-set change; no
statistical-significance testing anywhere in the codebase; an
unauthenticated prototype API. Full list, with rationale:
`docs/paper/limitations_draft.md`, `docs/research_handoff.md`,
`docs/CircadianIQ_Final_Master_Specification.md` §21.

## 19. Scientific boundary

Repeated deliberately, because it is the single most important
constraint on this project: CircadianIQ **computationally estimates**
circadian phase from behavioral/environmental proxies. It is not a
diagnostic tool, has not been validated against real human DLMO
measurements, and every result in this release is a synthetic-data
benchmark. See §1 above and `docs/scientific_assumptions.md` for the
complete inventory of which numerical assumptions are literature-backed
(none, in this release) vs. project modeling assumptions vs.
engineering choices.

## 20. Future work

External real-world validation cohort with measured DLMO/melatonin
anchors; recalibration of every project-modeling-assumption constant
against real data; closing the 3 documented limitations above
(especially structured version provenance); ablation studies on
feature groups; a documented (not yet implemented) path from synthetic
to real human data, including the ethical/regulatory approval such a
study would require. See `docs/research_handoff.md` "Future real-data
path" and `docs/paper/future_work_draft.md` for the full discussion.

---

The sections below are the project's phase-by-phase historical build
record (Phases 1-18, each one's "what it contains / deliberately does
NOT contain"), preserved as-is for provenance. For the current,
consolidated state of the system, see
`docs/CircadianIQ_Final_Master_Specification.md` and the numbered
sections above.

## What Phase 1 contains

- Full repository/package structure for the whole system.
- A configuration layer (`AppConfig` / `load_config`).
- A database connection + transaction abstraction (SQLite implemented,
  PostgreSQL scaffolded).
- Centralized logging setup.
- A startup health check verifying config, directories, and DB
  abstraction instantiation.
- Pytest infrastructure covering all of the above.

## What Phase 2 contains

- The complete relational schema (14 tables) for participants,
  daily observations, physiology, circadian predictions, alignment,
  contributors, the intervention catalogue and log, personalization
  state, missing-data audit, safety flags, and training-run metadata.
- SQLAlchemy ORM models (`app/database/models/`), portable across
  SQLite and PostgreSQL.
- Alembic migrations (`migrations/`) as the schema source of truth.
- A seed mechanism for the static recommendation catalogue only.
- Database tests covering schema creation, constraints, and
  longitudinal/immutability behavior.

See `docs/database_architecture.md` for the full design, including
normalization decisions, immutable-vs-mutable tables, and
SQLite/PostgreSQL portability notes.

## What Phase 2 deliberately does NOT contain

- Synthetic dataset generation (Phase 3).
- Feature engineering logic.
- The XGBoost model, the state model, or any DLMO fusion equations.
- Alignment-scoring, contributor-ranking, or recommendation-selection
  algorithms (the tables exist; the logic that fills them does not).
- Personalization or safety-detection algorithms (the tables exist;
  the logic that fills them does not).
- Any API or user interface.
- Any hard-coded scientific constants, effect sizes, or thresholds.
- Seeded participant history of any kind.

## What Phase 3 contains

- A synthetic population + 30-day longitudinal behavioral/physiological
  data generator (`app/synthetic/`), producing 1,000 participants x 30
  days (30,000 daily records) plus 24,000 sliding-window records (six
  days of behavior -> next-day DLMO target).
- A stateful three-layer DLMO model (intrinsic -> adapted -> current)
  driven by behavior generated independently of that state, with
  documented interaction effects and reproducible, subsystem-separated
  randomness.
- An explicit, config-driven split between source-backed assumptions
  (cited from `CircadianIQ_Project_Document.docx`) and synthetic
  modeling assumptions -- see `docs/synthetic_data_generation.md`.
- 16 automated quality checks, a distribution-diagnostics report with
  6 plots, Parquet/manifest export, and a CLI
  (`python -m app.scripts.generate_synthetic_data`) that writes into
  the Phase 2 schema (never a separate database).

See `docs/synthetic_data_generation.md` for the full design, including
the participant/personality/DLMO-model writeup and the literature vs.
synthetic assumption boundary.

## What Phase 3 deliberately does NOT contain

- ML feature engineering (turning the 6-day windows into the 68-feature
  representation) -- Phase 4.
- XGBoost training, the state model, or DLMO fusion.
- Alignment, contributor-ranking, or recommendation-selection logic.
- Personalization or safety-detection logic.
- Any API or user interface.
- Any fabricated citations; every non-cited numeric constant is labeled
  a synthetic assumption in `app/synthetic/config.py`.

## What Phase 4 contains

- The Version-1 feature engineering layer (`app/features/`): turns
  exactly six previous complete days of a participant's behavior into
  the 68-feature vector used to predict the next day's `current_DLMO`.
- A single authoritative, machine-readable feature manifest
  (`app/features/feature_manifest.py`) that the builder generates
  features *from* -- not an undocumented list scattered across files.
- Reusable circular time encoding (`clock_to_sincos`/`sincos_to_clock`),
  a single recency-weighting utility, and a 3-tier missing-data
  fallback chain (window -> personal history -> population default).
- Structural enforcement of the anti-circularity rule (no sleep-onset/
  offset/midpoint feature) and the Version-1 architecture lock (no
  physiology feature) -- both re-checked by 15 automated sanity checks.
- A CLI (`python -m app.scripts.build_feature_dataset`) that builds and
  exports the full feature matrix (24,000 rows x 68 features for the
  Phase 3 dataset) as Parquet, plus a statistical diagnostics report.

See `docs/feature_engineering.md` for the complete 68-row feature
manifest, the anti-circularity rationale, and the assumptions behind
recency weighting and the MEQ/MSFsc divergence feature.

## What Phase 4 deliberately does NOT contain

- XGBoost training, model evaluation, or daily inference (Phase 5).
- DLMO fusion, alignment scoring, or contributor ranking.
- Recommendation selection, personalization, or safety logic.
- Any API or user interface.
- Any global fitting/scaling of the feature matrix (tree-based models
  don't need it, and fitting anything here would risk leakage).

## What Phase 5 contains

- The XGBoost DLMO training + validation pipeline (`app/models/`):
  participant-level train/test split (800/200), 5-fold `GroupKFold`
  cross-validation, two independent `XGBRegressor` models
  (`sin`/`cos`), held-out test evaluation, and two non-learned
  baselines.
- Circular-time evaluation utilities (`circular_error_minutes`,
  `compute_metrics`) computing MAE/RMSE/median/percentile-within-band
  metrics correctly across midnight, plus personality-, chronotype-,
  and completeness-stratified breakdowns.
- Feature importance (gain-based) and SHAP diagnostics -- interpretive
  only, never wired into production logic.
- Versioned model artifacts (`models/xgboost_dlmo_{sin,cos}_v*.pkl` +
  `model_metadata_v*.json`, never overwritten) and a `training_runs`
  database row per run (Phase 2's schema, unmodified).
- A CLI (`python -m app.scripts.train_model`) running the full
  pipeline end to end.
- **Result on the synthetic held-out test set**: MAE 24.47 min, 93.73%
  within +/-60 min -- reaching the project's "excellent" success tier.
  This is a synthetic-data result and does not demonstrate real-human
  performance (see `docs/model_training_and_validation.md`).

See `docs/model_training_and_validation.md` for the complete
evaluation report: CV fold results, baselines, stratified metrics,
feature importance/SHAP, and limitations.

## What Phase 5 deliberately does NOT contain

- Daily production inference, DLMO fusion, or the state engine (Phase 6).
- Alignment scoring, contributor ranking, or recommendation selection.
- Personalization or safety logic.
- Any API or user interface.
- Hyperparameter search (the baseline configuration is used as-is; the
  code is structured so tuning can be added later without touching the
  pipeline itself).

## What Phase 6 contains

- The three-layer state engine (`app/state/`): `intrinsic_DLMO ->
  adapted_DLMO -> current_DLMO`, computed purely from behavioral
  history and state continuity -- independent of, and never importing,
  the trained XGBoost model.
- The single authoritative behavioral-effect model
  (`app.state.behavioral_effect`), shared by the Phase 3 synthetic
  generator (which now delegates to it via a thin backward-compatible
  translation layer, `app.synthetic.dlmo_state`) and available for
  future production inference -- there is no duplicated copy of these
  equations anywhere in the codebase.
- Explicit deterministic (`step`) vs. stochastic (`step_stochastic`)
  entry points, so production inference never has hidden randomness.
- A trajectory replay function (`app.state.replay`) and 10 automated
  state sanity checks (`app.state.sanity`).
- Read-side Phase 2 database adapters (`app.state.db_adapter`) and
  diagnostic plots for 5 example participant archetypes
  (`app.state.diagnostics`).
- **Verified refactor safety**: regenerating the full Phase 3 dataset
  after this refactor reproduces the previously-stored values to
  within database time-rounding precision; a dedicated test proves
  exact (1e-9) equivalence under a noise-free configuration.

See `docs/state_engine.md` for the complete design writeup: the state
equations, every configuration parameter, temporal ordering rationale,
circular-time handling, and the synthetic-vs-scientific disclaimer.

## What Phase 6 deliberately does NOT contain

- XGBoost training or inference integration, or DLMO fusion (Phase 7).
- Alignment scoring, contributor ranking, or recommendation selection.
- Personalization or safety logic.
- Any API or user interface.
- Writing state-engine output back to the database (only read-side
  adapters exist; Phase 7's fusion layer owns producing the
  authoritative `circadian_labels` row).

## What Phase 7 contains

- The DLMO fusion layer (`app/fusion/`): combines the Phase 5 XGBoost
  estimate and the Phase 6 state-engine estimate into one fused DLMO,
  via the locked four-layer Q26 model -- base weights from data
  quality, a disagreement-based weight adjustment, a biological
  continuity constraint anchored on the previous *fused* DLMO, and a
  confidence penalty.
- Correct circular fusion (weighted unit-circle vectors, never naive
  hour averaging) with a documented, non-random fallback for the
  zero-magnitude edge case.
- Explicit model-availability handling (XGB-only, state-only, or
  neither available) kept structurally separate from data-quality
  handling.
- A no-prediction rule that can override a mathematically-computed
  fused value when upstream data quality doesn't support a user-facing
  prediction.
- A diagnostic experiment (`python -m app.scripts.run_fusion_diagnostics`)
  run once over the Phase 5 held-out test set, with **no fusion
  parameter tuned against it** -- see `docs/dlmo_fusion.md` for the
  important caveat about what that experiment can and cannot
  demonstrate on synthetic data.

See `docs/dlmo_fusion.md` for the complete design writeup: every
parameter table, the circular-fusion math, worked midnight and
continuity-limiting examples, and the scientific limitations.

## What Phase 7 deliberately does NOT contain

- The alignment engine, contributor ranking, or recommendation
  selection (Phase 8).
- Personalization or safety logic.
- Any API or user interface.
- Daily production inference (fusion is pure computation here; a
  future pipeline phase calls it, this phase does not run it end to
  end against live data on a schedule).
- Any claim that fusion improves real-world DLMO accuracy, or that
  this is an actual Kalman filter.

## What Phase 8 contains

- The alignment engine (`app/alignment/`): converts the Phase 7 fused
  DLMO and a participant's actual behavior into a personalized 0-100
  alignment score, `0.60 * phase_alignment + 0.40 * behavioral_alignment`.
- Phase alignment: actual sleep onset vs. an "ideal" sleep onset
  (`fused DLMO + 2h`, a documented project assumption) via a circular
  exponential-decay score curve -- verified against both worked
  examples in the brief (+15 min -> high score; a midnight-crossing
  case where the naive linear difference would be wildly wrong).
- Behavioral alignment: 5 weighted components (sleep consistency 25%,
  morning light 25%, evening screen 20%, meal timing 15%, social
  jetlag 15%), each over the six-day window, reusing Phase 3/6's tier
  classifiers rather than redefining behavioral thresholds a third
  time. MEQ is never used (confirmed by a dedicated structural test).
- Explicit missing-data handling (window fallback -> neutral
  placeholder, never silently presented as directly observed) and a
  `data_completeness` / `imputed_components` accounting on every result.
- 8 automated sanity checks (`app.alignment.sanity`) covering
  monotonicity, bounds, weight validation, the MEQ exclusion, and
  re-confirming Phase 4's anti-circularity guarantee still holds.
- A diagnostic report (`python -m app.scripts.run_alignment_diagnostics`)
  over 800 synthetic participant-windows, showing alignment correctly
  differentiating behavioral personalities in the expected direction
  -- read with the same synthetic-data caveat as every prior phase's
  diagnostics.

See `docs/alignment_engine.md` for the complete design writeup,
including the full scoring-curve tables and the design-assumption-vs-
scientific-claim distinction.

## What Phase 8 deliberately does NOT contain

- Contributor ranking, recommendation selection, or intervention
  effectiveness (Phase 9).
- Personalization or safety logic.
- Any API or user interface.
- Writing alignment results back to the database (read-only; a future
  phase owns the `circadian_labels` write path).
- Any claim that a given alignment score reflects a universal healthy
  schedule, or that synthetic-data alignment distributions describe
  real human populations.

## What Phase 9 contains

- The contributor ranking engine (`app/contributors/`): identifies the
  top 3 behavioral signals (of exactly 5 candidates: evening screen,
  morning light, meal timing, social jetlag, exercise) contributing
  most to a participant's current misalignment,
  `contributor_score = 0.60 * normalized_phase_effect + 0.40 * alignment_deficit`.
- Phase-shift effects reused directly from Phase 6's
  `compute_behavioral_effect` (no second, contradictory effect model);
  alignment deficits reused directly from Phase 8's
  `behavioral_components` (no recomputation).
- A documented "mirror-image asymmetry" for the two signals missing
  one of the two composite inputs by construction: `exercise` is
  phase-effect-only (no fabricated alignment component), `social_jetlag`
  is deficit-only (no fabricated phase effect) -- neither ever receives
  an invented value for its missing side.
- Direction classification (`hurting` / `opportunity_missed` /
  `neutral`) relative to the participant's actual current phase
  deviation, plus a configurable significance threshold that prevents
  weak noise from looking like a meaningful contributor.
- **Today's anomaly detection**, using a robust median/MAD statistic
  (circular-aware for clock-time signals) against the participant's
  own six-day history -- kept strictly separate from, and verified to
  never alter, the six-day habit-level ranking.
- 9 automated sanity checks (`app.contributors.sanity`) plus 42
  dedicated tests (`tests/test_contributors.py`) covering scoring,
  normalization, the all-zero-effect case, direction classification,
  circular and zero-variance anomaly handling, missing/imputed data,
  determinism, and database read-compatibility.
- A diagnostic report (`python -m app.scripts.run_contributor_diagnostics`)
  over 600 synthetic participant-windows, showing contributor
  distributions correctly tracking each synthetic behavioral
  personality (e.g. `screen_heavy_user` -> `evening_screen`,
  `social_jetlag_student` -> `social_jetlag`) -- read with the same
  synthetic-data caveat as every prior phase's diagnostics.

See `docs/contributor_ranking.md` for the complete design writeup,
including the locked scoring formula, the signal/component mapping,
and a full worked example.

## What Phase 9 deliberately does NOT contain

- Recommendation selection, intervention effectiveness, or
  personalization (Phase 10).
- Safety detection, UI, or an API.
- Any natural-language explanation generation -- only structured
  numeric/metadata fields.
- Any causal claim -- output fields describe "modeled influence" /
  "estimated phase effect" / "alignment deficit," never "cause."
- A new alignment-confidence system, or any change to Phase 8's
  alignment scores.
- Writing contributor results back to the database (read-only; a
  future phase owns that write path, and no duplicate table is
  introduced).

## What Phase 10 contains

- The recommendation engine (`app/recommendations/`): converts Phase
  9's ranked contributors into exactly **1 primary intervention + up
  to 2 supporting nudges**, never three equal-priority suggestions,
  `candidate_score = relevance * (impact_weight*norm_impact + feasibility_weight*norm_feasibility) + personalization_adjustment + continuation_bonus`.
  Fully deterministic -- no LLM, no free-form text generation.
  Candidate interventions come **only** from the database catalogue
  (`recommendations` table, `app.database.seed`); nothing is
  hard-coded in Python.
- A misalignment-severity model (`good`/`mild`/`moderate`/`severe`
  from Phase 8's alignment score) driving severity-specific
  impact/feasibility weighting, favoring low-burden maintenance nudges
  for already-well-aligned participants.
- **Graduated targets**: never asks for the theoretically ideal value
  immediately -- targets roughly halfway to it
  (`graduated_target_fraction = 0.50`), using the existing circular
  time utilities so a screen-cutoff or meal-time target crossing
  midnight is computed as the short way around, not a naive 20+ hour
  linear difference (verified against the exact 01:30 -> 00:00 worked
  example from the brief).
- Contributor-relevance scoring so the primary intervention always
  targets the participant's own top-ranked, significant Phase 9
  contributor rather than whichever catalogue entry has the largest
  (placeholder) literature effect size.
- Cooldown/continuation handling (a currently-active primary is not
  needlessly displaced by a marginally higher-scoring alternative) and
  personalization-phase interface compatibility (`literature` /
  `personal_ranking` / `personal_effect` / `adaptive_policy`) without
  implementing the personal-effect model or bandit itself.
- 8 automated sanity checks (`app.recommendations.sanity`) plus 43
  dedicated tests (`tests/test_recommendations.py`) covering severity,
  scoring, graduated targets (including the circular midnight case),
  feasibility, cooldown, conflict resolution, missing data,
  determinism, template rendering, the no-medical-language guarantee,
  serializability, and database read-compatibility.
- A diagnostic report (`python -m app.scripts.run_recommendation_diagnostics`)
  over 600 synthetic participant-windows, showing primary-intervention
  selection correctly tracking each synthetic behavioral personality
  -- read with the same synthetic-data caveat as every prior phase.

See `docs/recommendation_engine.md` for the complete design writeup,
including the full worked example.

## What Phase 10 deliberately does NOT contain

- Intervention effectiveness measurement, long-term personalization
  algorithms, or a contextual bandit (a later phase) -- only the
  interface those phases will plug into.
- Safety detection (Phase 14), a UI, or an API.
- Any free-form or LLM-generated recommendation text -- only
  deterministic, database-sourced templates with structured variables
  filled in.
- Any medical recommendation (medication, melatonin dosing,
  diagnosis-based treatment) -- behavioral suggestions only.
- Writing selected recommendations back into `intervention_log` (the
  selection logic is deliberately kept separate from persistence; a
  future phase owns that write path).
- Any claim that a catalogue expected-improvement value is a verified
  scientific effect size -- every one is an explicitly labeled project
  placeholder.

## What Phase 11 contains

- The daily inference pipeline (`app/pipeline/`): one orchestrated
  workflow, `app.pipeline.orchestrator.run_daily_inference(participant_id, target_date, session_factory)`,
  connecting DATABASE -> Phase 4 features -> Phase 5 XGBoost + Phase 6
  state engine -> Phase 7 fusion -> Phase 8 alignment -> Phase 9
  contributors -> Phase 10 recommendation -> DATABASE. Pure
  orchestration: every step calls the existing phase's own public
  entry point, never a reimplemented formula.
- **Locked start-of-day timing**: Day N's prediction uses only Days
  `N-6..N-1`; the Q23 onboarding schedule (no prior state -> initialize;
  < 6 consecutive prior days -> state-only, no XGBoost; >= 6 -> full
  ML inference) determined and implemented here, since no earlier
  phase defined this day-counting gate.
- **One atomic write transaction** per daily result (`CircadianLabel`
  + `AlignmentResult` + `ContributorResult` rows + `InterventionLog` +
  `ParticipantProfile` current/adapted state) -- verified to roll back
  in full on any write failure, with no partial `CircadianLabel`
  insert and no partial `ParticipantProfile` mutation left behind.
- **Idempotency**: a repeated request for an already-computed
  participant/date returns the existing result without recomputing or
  duplicating any row; an explicit `force_rerun=True` supports a
  versioned rerun that supersedes (never silently overwrites) the
  prior row via the existing `is_latest` pointer.
- Full provenance on every result (pipeline/feature-manifest/model/
  state/fusion/alignment/contributor/recommendation config versions),
  persisted wherever the existing schema supports it
  (`training_run_id`, `AlignmentResult.component_snapshot`) and always
  returned in the structured result's diagnostics.
- A documented failure-handling policy distinguishing "feature engine
  failed" (abort, write nothing), "XGBoost failed alone" (fall back to
  Phase 7's own state-only path), and "alignment/contributor/
  recommendation failed" (abort -- never invent an alignment score).
- 22 dedicated tests (`tests/test_pipeline.py`) covering end-to-end
  success, six-day window correctness and no-leakage, insufficient
  history, each phase's integration, atomic rollback, idempotency,
  retry, deterministic replay (from a restored snapshot), and
  recommendation/state persistence consistency.
- A diagnostic run (`python -m app.scripts.run_pipeline_diagnostics`)
  over 50 synthetic participants x 2 target days: 100/100 successful,
  100% write success rate, 100% recommendation-generation rate,
  ~0.10s average runtime per inference.

See `docs/daily_inference_pipeline.md` for the complete design
writeup, including a sequence diagram and a full Day-10 worked
example.

## What Phase 11 deliberately does NOT contain

- Intervention feedback / effectiveness measurement (Phase 12).
- Any UI or dashboard -- only structured `DailyInferenceResult` data.
- Any REST API -- callable only directly from Python.
- A new pipeline-provenance database table; provenance not
  representable in the existing schema lives only in the returned
  result's diagnostics (see docs "Limitations").
- Retraining or fitting any model -- only loads the versioned Phase 5
  artifact specified in configuration.
- More than one persisted recommendation record per participant/date
  (only the primary is logged to `intervention_log`; supporting
  nudges remain in the structured result only).

## What Phase 12 contains

- The intervention feedback / effectiveness system (`app/effectiveness/`):
  measures whether a recommended intervention is **associated with**
  improved alignment, via a locked three-phase progression --
  `observational` (before/after) -> `matched_observational`
  (within-person matched-period) -> `regression_controlled_estimate`
  (personal linear regression) -- each phase's own sufficiency gate
  decides whether it is ever reported; the dispatcher never jumps to a
  stronger-sounding phase without enough data.
- Intervention-specific, asymmetric compliance scoring
  (`app.effectiveness.compliance`): full compliance at or past the
  target in the intervention's own desired direction, decaying only
  for shortfall, using circular time differences throughout (23:55
  before a midnight target is full compliance, never "23h55m off").
- Circular DLMO change/mean/slope handling in one authoritative module
  (`app.effectiveness.outcomes`) reused by all three phases -- no
  naive `recent_hour - baseline_hour` anywhere.
- Confound detection (`app.effectiveness.confound`): flags when a
  non-target behavior also changed substantially, without attempting
  causal adjustment -- surfaced as an explicit user-facing caveat.
- A new, purely additive table, `intervention_effect_estimates`
  (migration `a1b2c3d4e5f6`), storing one **immutable** row per
  computed evaluation -- recomputation always inserts a new row rather
  than overwriting history.
- A derived (never stored) intervention lifecycle
  (`RECOMMENDED -> ACTIVE -> OBSERVED -> EVALUATED`, or
  `INSUFFICIENT_DATA` / `WAITING_FOR_HISTORY`), fully reconstructable
  from `intervention_log`.
- Structured, phase-appropriate user-facing feedback data
  (`app.effectiveness.feedback`) -- fixed labels ("Observed change" /
  "Change compared with a similar previous period" / "Estimated
  personal effect"), never "caused," no natural-language generation.
- 30 dedicated tests (`tests/test_effectiveness.py`,
  `tests/test_effectiveness_db.py`) covering compliance, circular
  handling, all three phases, confounding, matching, regression
  confidence intervals, the phase dispatcher, persistence, and a
  full-stack recovery of a known synthetic ground-truth effect from a
  hand-built database scenario.
- A controlled simulation harness and diagnostic report (`python -m
  app.scripts.run_effectiveness_diagnostics`), since Phase 3's
  generator produces no intervention history automatically --
  explicitly labeled as injecting known effects for estimator
  validation, never presented as evidence about real participants.

See `docs/intervention_effectiveness.md` for the complete design
writeup, including worked examples.

## What Phase 12 deliberately does NOT contain

- Long-term personalization decision logic (Phase 13) -- this phase
  only produces the evidence that phase will consume.
- Any causal claim beyond what each phase's own design supports --
  "caused" / "proven effect" / "clinical effect" are never used.
- Any medical treatment, diagnosis, or medication recommendation.
- Alteration of the core Phase 3 synthetic generator to fabricate
  intervention history -- the diagnostic harness is a separate,
  explicitly labeled injection script.
- A contextual bandit or adaptive policy (that's this phase, Phase 13
  -- see below).
- Natural-language generation for user-facing feedback -- only fixed,
  structured labels and caveats.

## What Phase 13 contains

- The long-term personalization engine (`app/personalization/`):
  graduates each `(participant, intervention_type)` pair independently
  through `literature -> personal_ranking -> personal_effect ->
  adaptive_policy`, based purely on accumulated intervention-exposure
  and compliance evidence -- never on preference or model confidence.
- Personal ranking (`personal_score = |personal_effect| x compliance_probability`)
  and a personal effect curve (`effect = slope*compliance + intercept`)
  that **reuses Phase 12's Phase 3 regression coefficients directly**
  rather than refitting a second regression.
- Literature/personal blending (40%/60% below 21 observations, 100%
  personal above, always falling back to literature when the personal
  model fails one of six explicit validity checks).
- A lightweight contextual bandit with Thompson sampling
  (`app.personalization.bandit`) on the existing `bandit_state` table,
  using a textbook Normal-Normal conjugate update, with an explicit
  exploration-dominance safeguard so a clearly superior intervention is
  never displaced by arbitrary exploration.
- Strict temporal-leakage prevention (`app.personalization.db_adapter`)
  -- every evidence query takes an explicit `as_of_date` and only ever
  sees data strictly before it.
- A separate, offline update pipeline
  (`app.personalization.update.update_personalization_state`) distinct
  from daily inference -- daily inference only ever reads the current
  personalization state.
- Four additive columns on `personal_effect_models`
  (migration `bd2e1f4a9c31`) for confidence intervals, model version,
  and evidence source.
- 41 dedicated tests (`tests/test_personalization.py`,
  `tests/test_personalization_db.py`) covering graduation, ranking,
  blending, validity checks, the bandit's sampling/update/exploration
  behavior, temporal leakage, independent per-type graduation, two
  controlled synthetic scenarios (effect-dominant vs.
  compliance-dominant), and database persistence/auditability.
- A diagnostic report (`python -m app.scripts.run_personalization_diagnostics`)
  demonstrating a full cold-start -> `adaptive_policy` transition over
  simulated time, plus a controlled bandit simulation converging to
  ~99.7% selection of the higher-true-mean arm while still retaining
  measurable exploration.

See `docs/personalization_engine.md` for the complete design writeup,
including a full one-participant worked example across all phases.

## What Phase 13 deliberately does NOT contain

- The safety/confidence layer (Phase 14).
- Full deep reinforcement learning -- only a contextual bandit with
  Thompson sampling, explicitly restricted to the approved behavioral
  catalogue.
- Any causal claim -- "observed personal response" / "estimated
  personal effect" / "historical response," never "this intervention
  causes X."
- A second, duplicated Phase 12 effectiveness calculation -- personal
  effect estimates are always consumed from Phase 12's own persisted
  output.
- Tight coupling to Phase 10's internals -- personalization only
  supplies evidence/adjustments through the same interface fields
  Phase 10 already exposed for this purpose.

## What Phase 14 contains

- The safety + confidence layer (`app/safety/`):
  `prediction -> confidence gate -> pattern detection -> safety decision -> safe output contract`,
  callable after Phase 11 daily inference and before any application/
  API/UI output. Never modifies the underlying fused/intrinsic DLMO or
  any upstream model output -- only whether/how it is shown.
- **Confidence gating reused, never recomputed**: consumes Phase 7's
  own `FusionResult.final_confidence`/`confidence_label` directly
  (already the locked 80/60/40 bands) and maps them to
  `NORMAL`/`NORMAL_WITH_QUALIFIER`/`APPROXIMATE`/`NONE` display
  precision; the Q25 no-prediction rule (`prediction_made`) is read,
  never overridden.
- Four persistent unusual-pattern detectors over a rolling 14-day
  horizon (`persistent_late_phase`, `persistent_early_phase`,
  `continuous_dlmo_drift`, `low_alignment_despite_compliance`) --
  explicitly screening/escalation logic, never diagnosis; each
  requires >= 10 available observations and uses circular statistics
  throughout (a transparent, documented unwrap-and-OLS trend
  estimator correctly handles midnight-crossing trajectories).
- A `DETECTED -> PERSISTING -> RESOLVED` flag lifecycle with
  resolution hysteresis (7 consecutive normal observations), and a
  locked two-level severity model where only `continuous_dlmo_drift`
  is `HIGH` (suppresses the primary recommendation) and every other
  flag type is `MODERATE` (recommendation stays available alongside
  the flag).
- A hard-coded catalogue/language guard
  (`app.safety.catalogue_guard`) that blocks -- never merely logs --
  any recommendation outside the approved behavioral categories or
  containing medical/dosing language, plus a defensive scan
  (`app.safety.guardrails`) for explicit prohibited phrases ("you have
  DSWPD," "take melatonin at," etc.) verified never to false-positive
  on this layer's own legitimate disclaimer text.
- Nine additive columns (migration `c3f7a08e21b4`: five on
  `safety_flags` for audit/versioning, three on `circadian_labels` for
  joinless safety-status reads) -- no duplicate safety database.
- 52 dedicated tests (`tests/test_safety.py`, `tests/test_safety_db.py`)
  covering all 12 required scenarios (confidence tiers, each flag
  type, multiple simultaneous flags, resolution, invalid-recommendation
  blocking, midnight edge cases) plus property/invariant tests (no
  clinical-measurement claim, no diagnosis, HIGH always suppresses,
  MODERATE never auto-suppresses, safety never touches the fused DLMO).
- A diagnostic report (`python -m app.scripts.run_safety_diagnostics`)
  over 150 synthetic participants, confirming near-zero flag rate
  under ordinary synthetic trajectories and correct midnight-edge-case
  handling.

See `docs/safety_and_confidence.md` for the complete design writeup.

## What Phase 14 deliberately does NOT contain

- The application/API layer (Phase 15).
- Any diagnosis of a named sleep or circadian disorder -- screening/
  escalation language only, with a guardrail scan blocking specific
  prohibited phrases defensively.
- A second confidence computation -- confidence is always Phase 7's
  own `FusionResult` value, read-only.
- Any modification to the fused DLMO, intrinsic DLMO, XGBoost output,
  or any other upstream prediction -- this layer only decides
  visibility/framing.
- Medical treatment, medication, melatonin dosing, or clinical light-
  therapy guidance of any kind.

## What Phase 15 contains

- The application/API layer (`app/api/`): FastAPI routes ->
  application services -> the existing Phase 4-14 domain modules ->
  repositories -> database. Twelve versioned `/api/v1` endpoints
  (health, onboarding, participant profile, current status, daily
  inference, circadian history, behavior history, current
  contributors, current recommendation, intervention history +
  outcome submission, safety status).
- **Strict read/write separation**: `GET /status` and every other GET
  endpoint are pure database reads and never trigger inference;
  `POST /inference` is the only endpoint that computes anything, and
  it does so by calling `run_daily_inference` (Phase 11) followed by
  `SafetyEngine.evaluate` (Phase 14) in sequence -- composing, never
  reimplementing, either phase.
- Idempotency passed straight through from Phase 11: a repeated
  inference call for the same participant/date returns the existing
  result rather than duplicating it.
- Typed Pydantic request/response contracts throughout -- no route
  ever returns a raw SQLAlchemy object; every prediction-capable
  response carries the fixed `boundary_note` imported directly from
  `app.safety.messages`.
- Centralized error handling (`NotFoundError`/`ValidationFailedError`/
  `ConflictError`/`DependencyUnavailableError` -> 404/400/409/503;
  pydantic validation -> 422; anything unexpected -> a generic 500
  with the real exception logged server-side only) and a request
  correlation ID on every request/response/error.
- Two small additive migrations (`d4e8b19f3a2c`: `contributor_score`/
  `today_anomaly` on `contributor_results`, both already computed by
  Phase 9 but not previously persisted) enabling complete read-only
  API responses without recomputing anything.
- 34 dedicated tests (`tests/test_api.py`, `tests/test_api_flows.py`)
  covering every endpoint, validation, error handling, correlation
  IDs, the no-medical-language/no-raw-object invariants, and all four
  required end-to-end flows (onboard -> inference -> status; idempotent
  rerun; high-severity suppression; outcome submission -> history).
- A fixed, documented bug in Phase 11's trait-building code (a null
  `intrinsic_dlmo_time` crashed with an unguarded `AttributeError`
  instead of the clean `ValueError` the surrounding code already
  expected) -- only surfaced once a genuinely fresh (non-synthetic)
  onboarding path existed to trigger it.

See `docs/api_architecture.md` for the complete design writeup,
including the full endpoint catalogue and prototype security
limitations.

## What Phase 15 deliberately does NOT contain

- The user-facing UI/dashboard (Phase 16) -- this is an API only.
- Any new biological, ML, recommendation, personalization, or safety
  logic -- every computation is delegated to Phases 4-14 unchanged.
- Production authentication/authorization, rate limiting, or CORS/TLS
  configuration -- explicitly documented prototype limitations (see
  `docs/api_architecture.md` "Prototype security limitations").
- Computing an initial estimated biological clock from onboarding
  questionnaire data alone -- no phase implements a real MEQ/MCTQ ->
  DLMO formula; onboarding stores the baseline and a prediction
  becomes available once daily inference has real behavioral history
  to work with.

## What Phase 16 contains

- A standalone React 19 + TypeScript (Vite) dashboard (`frontend/`)
  that consumes the Phase 15 API exclusively -- no SQL access, no
  XGBoost import, and no DLMO/alignment/contributor/recommendation/
  personalization/safety computation in the UI. Every displayed value
  either comes directly from an API response or from a fixed,
  pre-approved terminology/messages lookup keyed off an API-provided
  enum.
- A centralized typed API client (`src/api/client.ts` +
  `src/api/types.ts`, hand-mirrored 1:1 from the Phase 15 Pydantic
  schemas) -- no component calls `fetch` directly.
- The primary dashboard: an estimated-biological-clock card with a
  circular, midnight-safe SVG clock visualization (DLMO estimate,
  ideal sleep onset, actual sleep onset); alignment score + 5-component
  breakdown; a confidence badge with the four required states (high /
  moderate / low / no-prediction, each with its approved wording); top
  contributors with strictly non-causal language and today's-anomaly
  shown as a visually distinct note; a primary recommendation with at
  most two supporting nudges (never three equal-weight suggestions);
  intervention progress; and a 7/30/90-day trajectory chart whose
  clock-time series is unwrapped for continuous midnight-crossing
  rendering (`unwrapHourSeries`, a TypeScript port of the existing
  circular-diff convention) without altering the underlying data.
- Full safety UI (none / moderate "Pattern note" / high safety message
  with the recommendation suppressed entirely, never dimmed or
  partially shown) and a no-prediction state that never fabricates or
  reuses a stale clock value.
- A 6-step onboarding flow and a daily behavioral data-entry form,
  backed by one genuinely new (and narrowly scoped) Phase 15 endpoint,
  `POST /participants/{id}/behavior`, since no prior phase exposed any
  way to get real behavioral data into the system outside the
  synthetic generator or direct DB access.
- Two additional minimal-compatibility backend extensions (documented,
  no new domain logic): exposing the already-computed alignment
  5-component breakdown and the already-computed ideal/actual sleep
  onset times on `GET /status` (migration `e5f9c27b4d8a` adds the two
  columns `AlignmentResult` was missing to persist Phase 8's own
  output).
- A design system (`styles/theme.css`) with light/dark support,
  responsive layout (single breakpoint, 2-column -> 1-column grid),
  and accessibility throughout (semantic landmarks, `role="progressbar"`/
  `role="alert"`/`role="status"`, real `<label>`s on every input,
  non-color-only indicators).
- 49 frontend tests across 16 files (Vitest + Testing Library):
  component-level coverage of every required area plus a dedicated
  integration/E2E suite (`src/test/integration.test.tsx`) mounting the
  real router and exercising onboarding, dashboard load, the inference
  action, post-inference status refresh, recommendation display,
  safety suppression, history loading, and daily-entry submission end
  to end against a mocked API.
- 657 passed / 1 skipped on the full Phase 1-16 backend regression
  suite (up from 654 passed pre-Phase-16, reflecting the 3 new tests
  for the daily-entry endpoint) -- confirming the additive backend
  changes broke nothing in Phases 1-15.

See `docs/ui_architecture.md` for the complete design writeup,
including component hierarchy, state management, terminology tables,
and documented limitations.

## What Phase 16 deliberately does NOT contain

- Any biological, ML, alignment, contributor, recommendation,
  personalization, or safety computation -- all of it stays in
  Phases 4-14, consumed read-only through the Phase 15 API.
- A full item-level MEQ/MCTQ questionnaire -- Phase 15's onboarding
  endpoint only accepts an aggregate `meq_score` and a single
  `msfsc_time`; the UI collects exactly those fields rather than
  inventing client-side scoring logic.
- A manual "did you follow this recommendation?" confirmation UI --
  compliance is derived automatically from logged behavior by
  Phase 12, not self-reported, so `POST
  /interventions/{id}/outcome` has no UI action in this phase.
- Complex global state management (Redux/react-query/etc.) -- local
  component state plus two small custom hooks (`useFetch`/`useAction`)
  cover every need.
- System-wide/cross-phase testing and validation (Phase 17) -- this
  phase's tests cover the UI layer and its documented API contract
  only.

## What Phase 17 contains

Phase 17 is a system-wide adversarial audit across all 16 completed
phases -- database through UI -- not a new feature phase. It added
**349 new backend audit tests** (`tests/audit/`) and **18 new frontend
audit tests** (`frontend/src/test/`), all executable adversarial
proofs (constructed leakage-injection cases, midnight-crossing
stress tests, forced-failure injection, a temporal replay proof for
personalization, a repository-wide medical-language grep scan, etc.)
rather than read-throughs, plus a standalone performance-measurement
script (`scripts/audit_performance.py`).

**6 real defects were found and fixed**, each with a regression test:
a circular-time bug in meal-timing scoring for post-midnight meals
(`app/state/behavioral_effect.py`), two related raw-exception-leak
defects in the inference API's failure responses
(`app/api/services/inference_service.py`), two unguarded pipeline
stages that could crash instead of failing gracefully
(`app/pipeline/orchestrator.py`), and an Alembic-in-process logging
bug that silently disabled application error logging
(`migrations/env.py`). **3 gaps were found and deliberately left
unfixed** (documented, not defects requiring urgent action): no
database-level uniqueness constraint on `circadian_labels.is_latest`,
incomplete structured version-provenance columns across result
tables, and a catalogue-lookup function that isn't `as_of_date`-scoped
(participant behavioral data itself is correctly scoped throughout).

**No participant leakage, no temporal leakage, and no safety/medical-
boundary violation was found anywhere in the system.** Final combined
test count: 1006 backend passed / 1 skipped (explicitly gated opt-in
test) / 0 failed, plus 60/60 frontend tests, plus a clean production
build.

See `docs/system_validation_and_audit.md` for the complete 30-item
audit report, the full scientific-assumption inventory (every locked
weight/threshold in the system, classified literature-backed /
project-modeling-assumption / engineering-choice with file:line
citations), the reproducibility and performance reports, and the
final release recommendation.

**Final release status: CONDITIONAL PASS.** Every PASS-blocking
criterion (no leakage, no critical safety failure, sound transactions,
correct circular arithmetic, reproducibility, working API/UI contract)
is met; the status is conditional only on the 3 documented,
non-critical limitations above, none of which caused an observed
incorrect output during this audit.

## Synthetic-data warning

**Every metric, weight, and evaluation result in this repository is
computed on synthetic data.** No CircadianIQ component has been
validated against real human circadian/DLMO measurements. Model
accuracy figures (`docs/model_training_and_validation.md`) describe
performance on held-out *synthetic* test windows only and must never
be read or repeated as a claim about real-human accuracy. Several
weights and thresholds (state-transition rates, fusion weights,
alignment weights, safety-pattern thresholds) are project modeling
assumptions or engineering choices, not literature-validated
constants -- see `docs/system_validation_and_audit.md` §26 for the
complete, file-cited inventory of which is which.

## What Phase 17 deliberately does NOT contain

- Any redesign of Phases 1-16's architecture -- every fix is a
  targeted, minimal correction to a defect the audit itself proved,
  with a regression test, never a rewrite.
- A resolution of the 3 documented limitations above -- each requires
  a schema/design decision (a partial unique index, structured
  provenance columns across multiple tables, or catalogue
  effective-dating) beyond what a same-phase bug fix should attempt.
- Load/production-scale performance testing -- Phase 17 measured
  wall-clock time at n=1/10/100 participants on one machine; it did
  not load-test or optimize anything.
- The final research/demo/reproducibility package (Phase 18).

## What Phase 18 contains

Phase 18 is a **packaging/freeze phase, not a development phase** --
it modifies no application algorithm, weight, or threshold. It:

- Freezes a single version manifest (`release/version_manifest.json`)
  identifying every component's version (database schema, feature
  manifest, synthetic generator, state/fusion/alignment/contributor/
  recommendation/effectiveness/personalization/safety config versions,
  API version, UI version, XGBoost model version "v1.1") with file:line
  sources, and flags the one genuine version-label inconsistency found
  (`feature_manifest_version`: "phase4-v1" in the trained model's own
  metadata vs. "1.0.0" in current code -- a naming mismatch, not a
  feature-set change).
- Adds a one-command reproduction script
  (`app/scripts/reproduce_release.py`) that composes the existing,
  individually-tested pipeline scripts against a **disposable**
  database (never the real dev DB by default), and a reproducibility
  manifest (`release/reproducibility_manifest.json`) documenting
  exactly what is and isn't guaranteed to be bit-identical to the
  original training run (`docs/reproducibility.md`).
- Adds a deterministic demo-scenario seeder
  (`app/scripts/seed_demo_scenarios.py`) producing 4 real participants
  (NORMAL, LOW_CONFIDENCE, MODERATE_SAFETY_FLAG, HIGH_SAFETY_FLAG) in a
  dedicated demo database, selected/verified by actually running the
  real pipeline end to end (one participant's DLMO trajectory is
  deliberately, disclosedly hand-authored rather than emergent, to
  reliably demonstrate the HIGH-severity safety boundary -- see
  `release/demo/demo_scenarios.json`), plus a 5th scenario
  (PERSONALIZATION_MATURE) honestly documented as not-yet-seeded rather
  than silently omitted.
- Preserves the validated Phase 5 ML results exactly
  (`models/model_metadata_v1.json`) and republishes them as
  machine-readable CSVs (`release/results/*.csv`) and figures
  (`release/figures/*.png`), without recomputing a single number.
- Pins exact dependency versions for release reproduction
  (`requirements-lock.txt`), generates SHA-256 checksums for every
  release-critical file (`scripts/generate_checksums.py` ->
  `release/checksums.sha256`), and bumps the frontend's own version
  field (`0.0.0` -> `1.0.0`) to track the release (no UI code changed).
- Produces the final documentation set: `docs/final_database_design.md`,
  `docs/dbms_demo_queries.sql`, `docs/final_ml_methodology.md`,
  `docs/scientific_assumptions.md`, `docs/research_methodology.md`,
  `docs/paper/*` (7 IEEE-style draft sections), `docs/demo_runbook.md`,
  `docs/architecture_diagrams.md` (7 Mermaid diagrams),
  `docs/developer_handoff.md`, `docs/research_handoff.md`,
  `docs/quickstart.md`, `docs/release_notes.md`, `CHANGELOG.md`, and
  `docs/CircadianIQ_Final_Master_Specification.md` (the single
  consolidated technical specification).
- Preserves Phase 17's CONDITIONAL PASS verdict and all 3 documented
  limitations verbatim -- none were silently fixed during packaging.
- Re-ran the complete backend + frontend test suite, the production
  build, and a fresh release-regression check of every Phase 17
  critical criterion after all packaging changes landed. See
  `docs/release_notes.md` for the final counts and
  `release/version_manifest.json` for the final Phase 18 release
  status.

## What Phase 18 deliberately does NOT contain

- Any change to XGBoost metrics, fusion weights, alignment weights,
  recommendation scoring, safety thresholds, database schema design,
  or UI design -- this phase packages and documents the frozen Phase
  1-17 implementation, it does not tune or redesign it.
- A fix for any of the 3 documented Phase 17 limitations -- each
  requires a deliberate schema/design decision, explicitly deferred
  rather than silently resolved.
- Real human data, a real clinical validation study, or an
  implementation of the future real-data transition path -- only a
  documented plan for one (`docs/research_handoff.md`).
- A Phase 19. This is the final implementation phase; any future
  feature request creates a new version/release rather than modifying
  this frozen research/demo implementation.

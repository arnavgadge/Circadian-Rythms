# Developer Handoff

This document orients an engineer inheriting the CircadianIQ codebase
(release `v1.0.0-research-demo`, 2026-09-09). It assumes no prior
context beyond general Python/SQL/React experience.

For the release-level status of this codebase, see
`release/version_manifest.json` (Phase 18 release status) and
`docs/release_notes.md`. This document does not repeat that verdict;
it is about how the code is put together and how to work in it.

## Repository structure

```
app/            Python backend: all computation + the API
frontend/       React + TypeScript dashboard UI (Vite)
tests/          Backend test suite (pytest), including tests/audit/ (Phase 17)
docs/           Architecture and process documentation (one file per subsystem)
migrations/     Alembic migration chain (SQL schema history)
scripts/        Top-level operational scripts (DB init, checksums, environment check)
models/         Frozen trained model artifacts (XGBoost + metadata JSON)
data/           SQLite database files and generated/processed datasets (gitignored content)
release/        Phase 18 release packaging: manifests, checksums, results, figures, demo data
```

### `app/` subpackages, one line each

| Package | Role |
|---|---|
| `app/synthetic` | Synthetic participant/population generator, incl. the stateful DLMO simulator used as ground truth for training and demo data. |
| `app/features` | Builds the versioned ML feature set from raw SQL observations (windows, aggregation, imputation, time encoding, manifest). |
| `app/models` | XGBoost training, evaluation, baselines, model registry/versioning (`model_registry.next_version`). |
| `app/state` | The mechanistic (non-ML) circadian state-model estimator and its DB adapter. |
| `app/fusion` | Combines the XGBoost estimate and the state-model estimate into one fused DLMO with a confidence score. |
| `app/alignment` | Scores how well a participant's actual behavior aligns with their estimated phase. |
| `app/contributors` | Identifies and ranks the behavioral/environmental factors driving misalignment. |
| `app/recommendations` | Selects and scores candidate interventions from the recommendation catalogue. |
| `app/pipeline` | Orchestrates the daily inference run end-to-end (`orchestrator.py`). |
| `app/effectiveness` | Evaluates whether a delivered intervention actually changed outcomes (Phase 12 evidence pipeline). |
| `app/personalization` | Learns per-participant intervention-effect models and drives targeting/ranking from that evidence (Phase 13). |
| `app/safety` | The one authoritative confidence-gate/pattern-detection/suppression layer applied before any output leaves the pipeline (Phase 14). |
| `app/api` | FastAPI application: routers, schemas, services, repositories (Phase 15). |
| `app/database` | SQLAlchemy models, engine/connection/transaction management, and reference-data seeding — the sole source of truth. |

Each of these packages also has its own `config.py` (see "Where
configuration lives" below) and most have a `diagnostics.py` /
`sanity.py` module used by the corresponding `app/scripts/run_*_diagnostics.py`
script — read those before touching a subsystem's internals.

## How data flows

SQL is the authoritative source of longitudinal state. Nothing in the
Python layer holds state across requests/runs that isn't also in the
database — this is deliberate (see `README.md` "Architecture" and
`docs/architecture.md`).

The daily-inference flow (`app/pipeline/orchestrator.py:run_daily_inference`)
follows a strict **read everything -> compute everything -> write
atomically** pattern:

```
READ FROM SQL (features input, prior state, history)
    -> feature engineering
    -> XGBoost prediction + state-model prediction (in parallel, independent)
    -> DLMO fusion
    -> alignment
    -> contributors
    -> recommendation
    -> BEGIN one atomic write transaction -> COMMIT
```

No expensive computation ever happens while a write transaction is
open, and any failure short of persistence leaves the database
untouched — see the module docstring in `app/pipeline/orchestrator.py`
for the exact per-stage failure-handling contract (each stage
degrades to a reported `FAILED` result rather than raising an
unhandled exception, except XGBoost failure, which degrades further
to a state-only fusion fallback instead of failing the run).

## Database: source of truth

The SQLAlchemy models under `app/database/models/` are the schema of
record; `app/database/seed.py` seeds reference/catalogue data;
`app/database/engine.py` / `connection.py` / `transaction.py` manage
sessions and the atomic-write transaction boundary described above.
No subsystem bypasses SQL to hold its own persistent state.

## Training workflow

```
python -m app.scripts.train_model
```

Reads engineered features from the database (via `app/features`),
trains the XGBoost sin/cos circular-regression model, evaluates it,
and writes versioned artifacts under `models/`. Training **never
overwrites a prior model version** — `app.models.model_registry.next_version`
scans existing artifacts and always picks a fresh version number; the
release-frozen artifacts (`models/xgboost_dlmo_sin_v1.pkl`,
`models/xgboost_dlmo_cos_v1.pkl`, `models/model_metadata_v1.json`,
model_version `v1.1` per `models/model_metadata_v1.json`) are safe
from being clobbered by a future training run.

## Inference workflow

```python
from app.pipeline.orchestrator import run_daily_inference
```

Runs the flow described above for one participant/date. This is what
the API calls per-participant; it is also what `app/scripts/seed_demo_scenarios.py`
and `app/scripts/reproduce_release.py` call in-process to populate
demo/reproduction databases.

## Personalization workflow

`app/personalization/update.py` is a **separate, offline** process
from daily inference:

```
intervention history
    -> Phase 12 effectiveness evidence (evaluate + persist)
    -> personal-effect model refresh
    -> phase determination
    -> personal_effect_models upsert
```

Daily inference only ever *reads* the resulting personalization state
(via `app.personalization.dispatcher`); it never triggers this update
pipeline itself. All personalization reads/writes are `as_of_date`-scoped
(see `app/personalization/db_adapter.py`) so that historical replay
never leaks future information — this was explicitly verified by a
temporal-replay proof in Phase 17, with one cataloged exception (see
Known Limitations, #3 below).

## Safety workflow

`app/safety/engine.py: SafetyEngine.evaluate()` is the one
authoritative safety layer; no safety logic is embedded anywhere else
in the pipeline:

```
prediction -> confidence gate -> pattern detection -> highest severity
    -> validate recommendation safety -> suppress if required
    -> construct output -> record decision
```

It never modifies the underlying fused DLMO or any upstream model
output — it only decides whether/how to *show* what upstream phases
already computed. Called after daily inference and before any
application/API/UI output.

## How to add a new intervention

Interventions live in the `Recommendation` catalogue table
(`app/database/models/recommendations.py`), seeded by
`app.database.seed.seed_reference_data` (`app/database/seed.py`,
`seed_reference_data`, around line 191). Concretely:

1. Add a new entry to the reference-data list that `seed_reference_data`
   iterates over in `app/database/seed.py` (each entry is passed as
   `Recommendation(**entry)` — follow the existing entries' fields:
   `intervention_type`, description/label fields, applicability
   criteria, and `is_active`).
2. Re-run seeding against your target database (via `scripts/init_db.py`,
   or the seeding step inside `app/scripts/reproduce_release.py` /
   `app/scripts/seed_demo_scenarios.py`).
3. The recommendation engine (`app/recommendations/engine.py` and its
   `scoring.py` / `relevance.py` / `feasibility.py` / `targets.py`
   collaborators) automatically considers any catalogue row with
   `is_active=True` — no code change is required in the engine itself
   to make a new intervention selectable, provided it fits the
   existing catalogue schema.
4. If the new intervention needs bespoke feasibility/relevance logic
   beyond the generic scoring, extend `app/recommendations/feasibility.py`
   / `relevance.py` accordingly, and add coverage under `tests/`.
5. Safety catalogue guarding (`app/safety/catalogue_guard.py`) applies
   to every catalogue row automatically — verify a new intervention
   doesn't need an explicit guard-rule addition there too.

## How to retrain a model

```
python -m app.scripts.train_model
```

or, to retrain as part of a full reproduction run:

```
python -m app.scripts.reproduce_release --retrain
```

Either path is safe to run against the frozen release artifacts —
`next_version` never overwrites `models/xgboost_dlmo_*_v1.pkl`.

## How to reproduce results

```
python -m app.scripts.reproduce_release
```

Targets a disposable database (never the developer's real
`data/circadianiq.db`), and supports `--participants`, `--days`,
`--seed`, `--retrain`, `--reset`, `--db-name`. It composes the
already-tested pipeline scripts (synthetic generation, feature
building, optional training, in-process daily inference, diagnostics)
rather than reimplementing them, and writes a timing/seed/environment
record to `release/reproducibility_manifest.json`. See
`docs/reproducibility.md` for the full walkthrough if present, or the
script's own module docstring in `app/scripts/reproduce_release.py`
otherwise.

## Where configuration lives

Every computational subsystem has its own `app/<subsystem>/config.py`
holding a versioned dataclass (e.g. `SyntheticConfig.config_version`,
`StateEngineConfig.state_config_version`, `FusionConfig.fusion_config_version`,
`AlignmentConfig.alignment_config_version`, `ContributorConfig.contributor_config_version`,
`RecommendationConfig.recommendation_config_version`,
`EffectivenessConfig.effectiveness_config_version`,
`PersonalizationConfig.personalization_config_version`,
`SafetyConfig.safety_config_version`, `PipelineConfig.pipeline_config_version`,
`TrainingConfig.config_version`). No subsystem reads ad-hoc
environment variables for its scientific parameters; environment
variables (`.env`, `app/config/`) control deployment-level concerns
(database URL, data directories, log level) only. See
`release/version_manifest.json` for the current value and file:line
source of every one of these versions as frozen for this release.

## Where scientific assumptions live

`docs/scientific_assumptions.md` is the destination for the modeling
assumptions behind the synthetic generator, the state model, and the
fusion/alignment weighting (produced alongside this document as part
of Phase 18 packaging). If it is not yet present when you read this,
it is expected imminently; until then, the per-subsystem docs already
in `docs/` (`synthetic_data_generation.md`, `state_engine.md`,
`dlmo_fusion.md`, `alignment_engine.md`, etc.) are the authoritative
description of each subsystem's assumptions.

## Known limitations (carry these forward — do not "fix" silently)

1. **No DB-level uniqueness constraint on `circadian_labels.is_latest`.**
   Enforced by application discipline only, in
   `app/database/models/circadian.py` (see the `is_latest` field and
   its surrounding docstring/index, `ix_circadian_labels_participant_latest`).
   A partial unique index (e.g. on `(participant_id) WHERE is_latest`)
   would close this at the schema level; it has not been added.

2. **Structured version-provenance columns are incomplete.** Only the
   XGBoost model version is a queryable column:
   `CircadianLabel.training_run_id -> TrainingRun.model_version`
   (`app/database/models/circadian.py`). Pipeline/fusion/state/alignment/
   recommendation config versions exist only inside the opaque
   `AlignmentResult.component_snapshot` JSON blob (also
   `app/database/models/circadian.py`). `ContributorResult`
   (`app/database/models/circadian.py`) and `InterventionLog`
   (`app/database/models/recommendations.py`) carry no version
   information at all.

3. **`app.personalization.db_adapter.latest_recommendation_id_for_type`
   is not `as_of_date`-scoped** — it always reads the catalogue's
   *current* active row for an intervention type
   (`app/personalization/db_adapter.py`, function
   `latest_recommendation_id_for_type`), rather than the row active as
   of a given historical date. This is a catalogue-versioning gap,
   **not** a participant-data leak — participant behavioral/outcome
   data is correctly `as_of_date`-scoped everywhere else, verified by
   an explicit temporal-replay proof in Phase 17.

See `docs/release_notes.md` and `release/version_manifest.json` for
the full, current statement of these limitations at release time.

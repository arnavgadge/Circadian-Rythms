# Reproducibility (Phase 18)

**Release:** `v1.0.0-research-demo`. This document describes exactly how
to reproduce CircadianIQ's major outputs -- the synthetic pipeline, the
demo scenarios, and (optionally) model training -- from a clean
environment. It does **not** claim bit-for-bit reproduction of the
original Phase 5 training run's exact numeric results (see "What is
and isn't guaranteed" below); it documents what actually is guaranteed
and why.

## The full sequence

```
CLEAN ENVIRONMENT
    -> INSTALL DEPENDENCIES        (pip install -r requirements-lock.txt; npm install)
    -> INITIALIZE DATABASE         (python scripts/init_db.py)
    -> GENERATE SYNTHETIC DATA     (python -m app.scripts.generate_synthetic_data)
    -> BUILD FEATURES              (python -m app.scripts.build_feature_dataset)
    -> TRAIN MODEL                 (python -m app.scripts.train_model -- optional, see below)
    -> VALIDATE MODEL              (same script; writes held-out test metrics + plots)
    -> RUN DAILY INFERENCE         (via the API, or run_daily_inference() directly)
    -> RUN EFFECT/PERSONALIZATION DEMOS  (python -m app.scripts.seed_demo_scenarios)
    -> GENERATE REPORTS            (diagnostics scripts; release/results/*.csv)
    -> START API                   (uvicorn app.api.main:app --reload)
    -> START FRONTEND              (cd frontend && npm run dev)
    -> RUN DEMO                    (docs/demo_runbook.md)
```

## One-command reproduction

```bash
python -m app.scripts.reproduce_release
```

This composes the existing, individually-tested scripts (it never
reimplements their logic) into one run:

1. `scripts/init_db.py` -- schema (Alembic `upgrade head`) + seed reference data.
2. `app.scripts.generate_synthetic_data` -- a synthetic population (default: a fast 60-participant/30-day smoke scale, not the full 1000; override with `--participants`/`--days`/`--seed`).
3. `app.scripts.build_feature_dataset` -- the 68-feature dataset built from the DB.
4. `app.scripts.train_model` -- **skipped by default**; pass `--retrain` to also run it.
5. The state/fusion/alignment/contributor/recommendation diagnostics scripts (`--skip-diagnostics` to skip).
6. A handful of real `run_daily_inference(...)` calls (`--inference-participants N`, default 5) -- a deterministic pipeline smoke scenario, not a training run.

It then writes `release/reproducibility_manifest.json` with the seed,
participant/day/window/feature counts, per-step timings, the Python
version, platform, and the relevant installed package versions.

### Safety: it never touches your real database

Every subprocess this script launches has `CIRCADIANIQ_DATABASE_URL`
pointed at a **disposable** SQLite file:
`data/<--db-name>.db` (default `--db-name release_reproduction`, i.e.
`data/release_reproduction.db`) -- never `data/circadianiq.db`. If you
explicitly pass `--db-name circadianiq`, the script refuses to run
unless you also pass `--reset` (the same explicit-opt-in pattern
`generate_synthetic_data.py --reset` already uses for participant
data). Delete the disposable database file freely at any time; nothing
about the release depends on it surviving.

Verified interactively at authoring time:

```
$ python -m app.scripts.reproduce_release --db-name circadianiq --participants 5
Refusing to target the real 'circadianiq' database without --reset. Use a disposable
--db-name (the default, 'release_reproduction') for a safe reproduction run.
```

### Example run (actual output, 15 participants / 30 days)

A real run at small scale completed in 9.1s end to end (schema init,
generation, feature build, 3 real inference calls, all `SUCCESS`); a
run including all 5 diagnostics scripts (12 participants/30 days)
completed in 37.9s. See `release/reproducibility_manifest.json` for
the exact fields recorded from the run that shipped with this release.

## What is and isn't guaranteed

**Guaranteed, and verified:**
- The synthetic generator is fully seed-deterministic: the same `--seed` always produces the same population, validated on every run via the generator's own built-in quality checks (participant/window counts, no duplicate participant-date rows, valid chronotype/personality distributions, DLMO bound compliance -- printed by the script itself).
- The daily-inference pipeline is deterministic given identical inputs: two runs off an identical database snapshot produce identical predictions, alignment, contributors, and recommendations (Phase 17 audit 21, `tests/audit/test_audit_reproducibility.py`).
- Personalization/bandit sampling requires an explicit caller-supplied RNG rather than unseeded global randomness (Phase 17 audit 21) -- this is what makes the adaptive-policy phase's reproducibility guarantee hold, not just the deterministic phases.
- The frozen model artifacts (`models/xgboost_dlmo_{sin,cos}_v1.pkl`) are never overwritten by this script by default; `--retrain` only adds a new version (`app.models.model_registry.next_version` never overwrites a prior one).

**NOT guaranteed to be bit-identical to the original Phase 5 training run:**
- `models/model_metadata_v1.json` records the exact library versions used to produce the validated `93.73% of held-out synthetic test windows within ±60 minutes` result: `xgboost==3.4.1`, `scikit_learn==1.9.0`, `joblib==1.6.0`, `pandas==3.0.5`, `numpy==2.5.3`. `requirements-lock.txt` (this release's dependency freeze) pins slightly different versions actually installed in this environment at packaging time (`xgboost==3.2.0`, `scikit-learn==1.8.0`, `joblib==1.5.3`, `pandas==3.0.1`, `numpy==2.4.3`) -- both sets pass the full test suite and reproduce the pipeline's *behavior*, but a fresh `--retrain` run under the currently-pinned versions is not guaranteed to reproduce the exact validated metrics to the decimal place. The validated numbers in `release/results/` and `models/model_metadata_v1.json` are the authoritative release numbers regardless of any later retrain; a retrain is a new, separately-versioned model artifact, not a replacement of the validated one.
- The default reproduction run's synthetic population (60 participants/30 days) is a much smaller scale than the original training population (1000 participants/30 days, 800/200 train/test split) purely for reproduction speed -- pass `--participants 1000` to match the original scale (this will take considerably longer).

## Reproducing the demo scenarios

```bash
python -m app.scripts.seed_demo_scenarios --reset
```

Generates a dedicated demo database (`data/demo.db`, never the real
dev DB) and classifies 4 real participants into the required demo
states (NORMAL, LOW_CONFIDENCE, MODERATE_SAFETY_FLAG, HIGH_SAFETY_FLAG)
by actually running the daily-inference and safety-evaluation pipeline
across each candidate's history and inspecting the genuine output --
not by hand-writing a result row. See `release/demo/demo_scenarios.json`
for the exact participant IDs and how each was selected (three are
naturally selected from a realistic synthetic population; the fourth,
HIGH_SAFETY_FLAG, has its DLMO trajectory directly authored rather
than emergent from realistic single-participant behavioral inputs --
disclosed in full in that manifest and in `docs/demo_runbook.md`).

## Environment facts recorded at this release's packaging time

| Fact | Value |
|---|---|
| Python | 3.14.3 |
| Node | v24.14.0 / npm 11.9.0 |
| OS | Windows-11-10.0.26200-SP0 |
| Database engine | SQLite (development/demo); PostgreSQL scaffolded but not exercised by this release |
| git commit | Not applicable -- no `.git` directory exists in this project environment. If you clone this into a git-tracked location, record `git rev-parse HEAD` alongside `release/version_manifest.json` yourself; the manifest's `git_commit` field is `null` for exactly this reason, not an oversight. |

See `release/version_manifest.json` for every component's version
(database schema, feature manifest, synthetic generator, state/fusion/
alignment/contributor/recommendation/effectiveness/personalization/
safety config versions, API version, UI version, XGBoost model
version) with file:line citations, and `requirements-lock.txt` /
`frontend/package-lock.json` for exact dependency pins.

## Known limitations (carried forward from Phase 17, unchanged)

1. No DB-level uniqueness constraint on `circadian_labels.is_latest`.
2. Structured version-provenance columns are incomplete.
3. `latest_recommendation_id_for_type` (personalization catalogue lookup) is not `as_of_date`-scoped.

None of these affect the reproducibility guarantees described above.

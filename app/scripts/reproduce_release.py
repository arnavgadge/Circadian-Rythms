"""Phase 18 one-command release-reproduction script.

    python -m app.scripts.reproduce_release
    python -m app.scripts.reproduce_release --participants 1000 --days 30 --seed 42
    python -m app.scripts.reproduce_release --retrain

Reproduces the CircadianIQ pipeline end to end against a **disposable**
database -- never the developer's real ``data/circadianiq.db`` -- by
composing the existing, already-tested scripts (never reimplementing
their logic):

    init schema + seed  -> scripts/init_db.py
    generate synthetic  -> app.scripts.generate_synthetic_data
    build features       -> app.scripts.build_feature_dataset
    train + validate      -> app.scripts.train_model   (opt-in, --retrain)
    run inference        -> app.pipeline.orchestrator.run_daily_inference (in-process)
    diagnostics reports  -> app.scripts.run_*_diagnostics
    write manifest        -> release/reproducibility_manifest.json

Safety: the target database is always ``data/<--db-name>.db`` (default
``release_reproduction.db``), set via the ``CIRCADIANIQ_DATABASE_URL``
environment variable for every subprocess this script launches. It
never points at the default ``data/circadianiq.db`` unless the caller
explicitly passes ``--db-name circadianiq``, in which case ``--reset``
is additionally required before this script will touch it -- the same
explicit-opt-in pattern ``generate_synthetic_data.py --reset`` already
uses for participant data.

By default this script does **not** retrain a model -- Phase 18 froze
``models/xgboost_dlmo_*_v1.pkl`` as the release artifact, and
retraining is slow and not needed to demonstrate reproducibility of
the *pipeline*. Pass ``--retrain`` to also run training; even then,
``persist_training_run`` (Phase 5) never overwrites a prior version --
see ``app.models.model_registry.next_version`` -- so the frozen v1
artifacts are safe either way.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--participants", type=int, default=60, help="Synthetic participants to generate (default: a fast smoke-scale run, not the full 1000).")
    parser.add_argument("--days", type=int, default=30, help="Days per participant.")
    parser.add_argument("--seed", type=int, default=42, help="Master synthetic-generation seed.")
    parser.add_argument("--db-name", type=str, default="release_reproduction", help="Disposable SQLite DB filename (without .db), under data/. Never the real 'circadianiq' DB unless --reset is also passed.")
    parser.add_argument("--reset", action="store_true", default=False, help="Delete the target DB file first if it exists. Required if --db-name circadianiq is used.")
    parser.add_argument("--retrain", action="store_true", default=False, help="Also run app.scripts.train_model (slow; writes a new versioned model artifact, never overwrites models/*_v1.pkl).")
    parser.add_argument("--inference-participants", type=int, default=5, help="How many generated participants to run a real daily-inference call for, as a smoke scenario.")
    parser.add_argument("--skip-diagnostics", action="store_true", default=False)
    return parser.parse_args(argv)


def _run(step_name: str, args: list[str], env: dict) -> float:
    print(f"\n{'=' * 70}\n>>> {step_name}\n{'=' * 70}")
    started = time.monotonic()
    result = subprocess.run([sys.executable, "-m", *args], cwd=str(PROJECT_ROOT), env=env, check=False)
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        raise SystemExit(f"Step failed: {step_name} (exit code {result.returncode})")
    print(f"--- {step_name} done in {elapsed:.1f}s ---")
    return elapsed


def _pip_freeze_relevant() -> dict:
    """A short, relevant subset of installed versions -- not a full env
    dump -- matching requirements-lock.txt's direct-dependency list."""

    names = ["xgboost", "scikit-learn", "pandas", "numpy", "joblib", "fastapi", "sqlalchemy", "alembic", "pydantic"]
    versions = {}
    for name in names:
        try:
            import importlib.metadata as md

            versions[name] = md.version(name)
        except Exception:
            versions[name] = None
    return versions


def main(argv=None) -> int:
    args = parse_args(argv)

    db_path = PROJECT_ROOT / "data" / f"{args.db_name}.db"
    if args.db_name == "circadianiq" and not args.reset:
        raise SystemExit(
            "Refusing to target the real 'circadianiq' database without --reset. "
            "Use a disposable --db-name (the default, 'release_reproduction') for a safe reproduction run."
        )
    if args.reset and db_path.exists():
        db_path.unlink()
        print(f"Removed existing disposable database: {db_path}")

    env = os.environ.copy()
    env["CIRCADIANIQ_DATABASE_URL"] = f"sqlite:///{db_path}"

    total_started = time.monotonic()
    timings: dict[str, float] = {}

    timings["init_db"] = _run("1/6 Initialize schema + seed reference data", ["scripts.init_db"], env)

    timings["generate_synthetic_data"] = _run(
        "2/6 Generate synthetic population",
        [
            "app.scripts.generate_synthetic_data",
            "--participants", str(args.participants),
            "--days", str(args.days),
            "--seed", str(args.seed),
        ],
        env,
    )

    timings["build_feature_dataset"] = _run("3/6 Build feature dataset", ["app.scripts.build_feature_dataset"], env)

    if args.retrain:
        timings["train_model"] = _run("4/6 Train + validate model (opt-in)", ["app.scripts.train_model"], env)
    else:
        print("\n(4/6 skipped: training. Pass --retrain to also retrain -- the release ships a frozen v1 model, not retrained by default.)")

    if not args.skip_diagnostics:
        for label, module in [
            ("state", "app.scripts.run_pipeline_diagnostics"),
            ("fusion", "app.scripts.run_fusion_diagnostics"),
            ("alignment", "app.scripts.run_alignment_diagnostics"),
            ("contributors", "app.scripts.run_contributor_diagnostics"),
            ("recommendations", "app.scripts.run_recommendation_diagnostics"),
        ]:
            timings[f"diagnostics_{label}"] = _run(f"5/6 Diagnostics: {label}", [module], env)
    else:
        print("\n(5/6 skipped: diagnostics, per --skip-diagnostics)")

    # --- 6/6: run a handful of real daily-inference calls in-process, as
    # a deterministic pipeline smoke scenario (not a training run) ---
    print(f"\n{'=' * 70}\n>>> 6/6 Run daily inference for {args.inference_participants} participant(s)\n{'=' * 70}")
    os.environ["CIRCADIANIQ_DATABASE_URL"] = env["CIRCADIANIQ_DATABASE_URL"]
    from sqlalchemy import select

    from app.config.settings import load_config
    from app.database.engine import create_app_engine, create_session_factory
    from app.database.models import DailyObservation, Participant
    from app.pipeline.orchestrator import run_daily_inference

    app_config = load_config()
    engine = create_app_engine(app_config)
    session_factory = create_session_factory(engine)
    inference_session = session_factory()
    participant_ids = inference_session.execute(
        select(Participant.id).order_by(Participant.id).limit(args.inference_participants)
    ).scalars().all()
    inference_results = []
    for pid in participant_ids:
        last_obs_date = inference_session.execute(
            select(DailyObservation.observation_date)
            .where(DailyObservation.participant_id == pid)
            .order_by(DailyObservation.observation_date.desc())
            .limit(1)
        ).scalar_one()
        result = run_daily_inference(pid, last_obs_date, session_factory)
        inference_results.append({"participant_id": pid, "target_date": str(last_obs_date), "status": result.status})
        print(f"  participant {pid} / {last_obs_date}: {result.status}")
    inference_session.close()

    total_elapsed = time.monotonic() - total_started

    # --- write the reproducibility manifest ---
    from app.features.feature_manifest import FEATURE_MANIFEST_VERSION, TOTAL_FEATURE_COUNT

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "release_version": "v1.0.0-research-demo",
        "reproduction_run": {
            "database_path": str(db_path),
            "participants": args.participants,
            "days": args.days,
            "seed": args.seed,
            "window_count_per_participant": max(0, args.days - 6),
            "total_window_count": args.participants * max(0, args.days - 6),
            "feature_count": TOTAL_FEATURE_COUNT,
            "feature_manifest_version": FEATURE_MANIFEST_VERSION,
            "retrained": args.retrain,
            "diagnostics_run": not args.skip_diagnostics,
            "inference_smoke_results": inference_results,
            "step_timings_seconds": {k: round(v, 2) for k, v in timings.items()},
            "total_runtime_seconds": round(total_elapsed, 2),
        },
        "environment": {
            "python_version": sys.version,
            "platform": platform.platform(),
            "relevant_package_versions": _pip_freeze_relevant(),
        },
        "git_commit": None,
        "git_note": "No .git directory present in this environment at manifest-generation time; commit hash unavailable.",
        "note": (
            "This manifest describes a REPRODUCTION run against a disposable database "
            f"({db_path.name}), using the default fast smoke-scale participant count. "
            "It does NOT overwrite the frozen release model artifacts in models/ unless "
            "--retrain was passed, and validated Phase 5 metrics in "
            "models/model_metadata_v1.json / release/results/ are the authoritative "
            "release numbers regardless of this run's own (different-scale) synthetic data."
        ),
    }
    manifest_path = PROJECT_ROOT / "release" / "reproducibility_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")

    print(f"\n{'=' * 70}")
    print(f"Reproduction complete in {total_elapsed:.1f}s. Manifest written to {manifest_path}")
    print(f"Disposable database left at: {db_path} (delete freely; it is not the release database)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())

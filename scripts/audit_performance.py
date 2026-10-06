"""AUDIT 24 -- Phase 17 performance measurement (measurement only, no
optimization).

Times, using ``time.perf_counter``, each stage of one day's inference
(feature generation, XGBoost inference, state computation, fusion,
alignment, contributor ranking, recommendation selection, and the
total ``run_daily_inference`` call), plus one representative API
response time, for 1 / 10 / 100 participants.

Usage::

    python -m scripts.audit_performance

This is a standalone diagnostic script (not a pytest test): it builds
a throwaway SQLite database under a temp directory, generates a real
synthetic population through the actual Phase 3 generator, and runs
the actual Phase 11 pipeline end to end. Nothing here is a claim about
production hardware performance -- it is a relative, single-machine
measurement to flag obvious bottlenecks for future work, per the
Phase 17 audit spec ("do not optimize prematurely").
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_MODELS_DIR = Path(__file__).resolve().parents[1] / "models"

from app.config.settings import AppConfig
from app.database.engine import create_app_engine, create_session_factory
from app.database.init_db import create_all_tables
from app.database.seed import seed_reference_data
from app.pipeline.orchestrator import run_daily_inference
from app.pipeline.read import read_daily_inference_inputs
from app.pipeline.state_step import run_state_step
from app.pipeline.traits import build_participant_traits, build_previous_state
from app.pipeline.xgboost_step import build_feature_step, run_xgboost_step
from app.pipeline.config import DEFAULT_PIPELINE_CONFIG
from app.state.config import DEFAULT_STATE_ENGINE_CONFIG
from app.fusion.config import DEFAULT_FUSION_CONFIG
from app.fusion.fuse import fuse
from app.alignment.db_adapter import build_alignment_inputs
from app.alignment.engine import compute_alignment
from app.contributors.db_adapter import build_contributor_inputs
from app.contributors.engine import rank_contributors
from app.recommendations.db_adapter import build_behavioral_history, load_candidate_interventions, load_prior_primary, load_recent_compliance
from app.recommendations.engine import select_recommendations
from app.recommendations.inputs import RecommendationInputs
from app.pipeline.quality import build_data_quality_input
from app.synthetic.config import DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC, SimulationRunConfig
from app.synthetic.db_writer import write_dataset_to_db
from app.synthetic.simulator import generate_synthetic_dataset
from app.synthetic.time_utils import clock_time_to_hour
from sqlalchemy import select
from app.database.models import Participant, DailyObservation


def _build_db(num_participants: int, num_days: int = 30, seed: int = 42):
    tmp = Path(tempfile.mkdtemp(prefix="circadianiq_perf_"))
    config = AppConfig(
        environment="testing", database_url=f"sqlite:///{tmp / 'perf.db'}", data_dir=tmp / "data",
        raw_data_dir=tmp / "data/raw", synthetic_data_dir=tmp / "data/synthetic",
        processed_data_dir=tmp / "data/processed", model_dir=Path(__file__).resolve().parents[1] / "models",
        log_level="ERROR",
    )
    engine = create_app_engine(config)
    create_all_tables(engine)
    factory = create_session_factory(engine)

    session = factory()
    seed_reference_data(session)
    session.close()

    sim_cfg = SimulationRunConfig(num_participants=num_participants, num_days=num_days, seed=seed)
    dataset = generate_synthetic_dataset(sim_cfg, DEFAULT_SOURCE_BACKED, DEFAULT_SYNTHETIC)
    write_dataset_to_db(dataset, factory)

    return factory, config


def _participant_ids(factory, limit: int) -> list:
    session = factory()
    try:
        return list(session.execute(select(Participant.id).order_by(Participant.id).limit(limit)).scalars().all())
    finally:
        session.close()


def _dates_for(factory, pid: int) -> list:
    session = factory()
    try:
        return list(
            session.execute(
                select(DailyObservation.observation_date)
                .where(DailyObservation.participant_id == pid)
                .order_by(DailyObservation.observation_date)
            ).scalars().all()
        )
    finally:
        session.close()


def _time_stage_breakdown(factory, participant_ids: list, target_dates: dict) -> dict:
    """Times each individual stage for every given participant, driving
    the exact same real functions the orchestrator calls (not a
    reimplementation) -- see app.pipeline.orchestrator for the
    reference sequence this mirrors."""

    stage_times = {
        "feature_generation": [], "xgboost_inference": [], "state_computation": [],
        "fusion": [], "alignment": [], "contributor_ranking": [], "recommendation_selection": [],
    }

    for pid in participant_ids:
        target_date = target_dates[pid]
        session = factory()
        try:
            read_result = read_daily_inference_inputs(session, pid, target_date, DEFAULT_PIPELINE_CONFIG)
            traits = build_participant_traits(read_result.profile, read_result.window_observations, DEFAULT_PIPELINE_CONFIG)
            previous_state = build_previous_state(read_result.profile)

            t0 = time.perf_counter()
            state_step = run_state_step(previous_state, read_result.window_observations, traits, target_date, DEFAULT_STATE_ENGINE_CONFIG)
            stage_times["state_computation"].append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            feature_step = build_feature_step(pid, target_date, session)
            stage_times["feature_generation"].append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            xgb_result = run_xgboost_step(feature_step.feature_vector, _MODELS_DIR, DEFAULT_PIPELINE_CONFIG)
            stage_times["xgboost_inference"].append(time.perf_counter() - t0)

            data_quality = build_data_quality_input(feature_step.feature_vector, DEFAULT_PIPELINE_CONFIG)
            previous_fused = (
                clock_time_to_hour(read_result.previous_label.fused_dlmo_time)
                if read_result.previous_label is not None and read_result.previous_label.fused_dlmo_time is not None
                else None
            )

            t0 = time.perf_counter()
            fusion_result = fuse(
                xgb_dlmo=xgb_result.xgb_dlmo_hour, state_dlmo=state_step.new_state.current_dlmo_hour,
                previous_fused_dlmo=previous_fused, data_quality=data_quality, config=DEFAULT_FUSION_CONFIG,
            )
            stage_times["fusion"].append(time.perf_counter() - t0)

            most_recent_obs = read_result.window_observations[-1] if read_result.window_observations else None

            t0 = time.perf_counter()
            alignment_inputs = build_alignment_inputs(
                fusion_result.fused_final, list(read_result.window_observations),
                most_recent_observation=most_recent_obs, chronotype=read_result.profile.chronotype_category,
            )
            alignment_result = compute_alignment(alignment_inputs)
            stage_times["alignment"].append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            contributor_inputs = build_contributor_inputs(
                traits, alignment_result, list(read_result.window_observations), latest_observation=most_recent_obs
            )
            contributor_result = rank_contributors(contributor_inputs)
            stage_times["contributor_ranking"].append(time.perf_counter() - t0)

            t0 = time.perf_counter()
            catalogue = load_candidate_interventions(session)
            behavioral_history = build_behavioral_history(
                list(read_result.window_observations), actual_sleep_onset_hour=alignment_inputs.most_recent_sleep_onset_hour
            )
            recent_compliance = load_recent_compliance(session, pid, target_date)
            prior_primary = load_prior_primary(session, pid, target_date)
            recommendation_inputs = RecommendationInputs(
                fused_dlmo_hour=fusion_result.fused_final, alignment_result=alignment_result,
                contributor_result=contributor_result, behavioral_history=behavioral_history,
                candidate_interventions=catalogue, participant_id=pid, today=target_date,
                recent_compliance_by_intervention=recent_compliance, prior_primary=prior_primary,
            )
            select_recommendations(recommendation_inputs)
            stage_times["recommendation_selection"].append(time.perf_counter() - t0)
        finally:
            session.close()

    return stage_times


def _time_total_pipeline(factory, participant_ids: list, target_dates: dict) -> list:
    times = []
    for pid in participant_ids:
        t0 = time.perf_counter()
        run_daily_inference(pid, target_dates[pid], factory, force_rerun=True)
        times.append(time.perf_counter() - t0)
    return times


def _time_api(config: AppConfig, participant_id: int) -> float:
    import os

    os.environ["CIRCADIANIQ_ENV"] = "testing"
    os.environ["CIRCADIANIQ_DATABASE_URL"] = config.database_url
    os.environ["CIRCADIANIQ_DATA_DIR"] = str(config.data_dir)
    os.environ["CIRCADIANIQ_MODEL_DIR"] = str(config.model_dir)

    from fastapi.testclient import TestClient

    from app.api.main import create_app

    app = create_app()
    with TestClient(app) as client:
        t0 = time.perf_counter()
        client.get(f"/participants/{participant_id}")
        return time.perf_counter() - t0


def _summary(label: str, values: list) -> str:
    if not values:
        return f"{label}: n/a"
    return (
        f"{label}: n={len(values)} mean={statistics.mean(values)*1000:.2f}ms "
        f"median={statistics.median(values)*1000:.2f}ms max={max(values)*1000:.2f}ms"
    )


def run_for_size(num_participants: int) -> dict:
    print(f"\n=== {num_participants} participant(s) ===")
    t_build0 = time.perf_counter()
    factory, config = _build_db(num_participants)
    build_seconds = time.perf_counter() - t_build0
    print(f"(setup: DB + synthetic generation for {num_participants} participants took {build_seconds:.2f}s -- not counted below)")

    participant_ids = _participant_ids(factory, num_participants)
    target_dates = {pid: _dates_for(factory, pid)[6] for pid in participant_ids}  # day 7

    stage_times = _time_stage_breakdown(factory, participant_ids, target_dates)
    for stage, values in stage_times.items():
        print(_summary(stage, values))

    total_times = _time_total_pipeline(factory, participant_ids, target_dates)
    print(_summary("run_daily_inference (TOTAL)", total_times))

    total_stage_sum = sum(sum(v) for v in stage_times.values())
    total_pipeline_sum = sum(total_times)
    if total_pipeline_sum > 0:
        dominant_stage = max(stage_times.items(), key=lambda kv: sum(kv[1]))
        dominant_fraction = sum(dominant_stage[1]) / total_stage_sum if total_stage_sum else 0.0
        print(f"Dominant stage (of measured stage time): {dominant_stage[0]} ({dominant_fraction*100:.1f}% of summed stage time)")

    return {"stage_times": stage_times, "total_times": total_times, "config": config, "participant_ids": participant_ids}


def main() -> None:
    results = {}
    for n in (1, 10, 100):
        t0 = time.perf_counter()
        results[n] = run_for_size(n)
        elapsed = time.perf_counter() - t0
        print(f"(measurement for n={n} took {elapsed:.1f}s wall-clock)")

    api_time = _time_api(results[1]["config"], results[1]["participant_ids"][0])
    print(f"\nAPI GET /participants/{{id}} response time: {api_time*1000:.2f}ms")

    print("\n--- Summary complete. See scripts/audit_performance.py docstring: measurement only, no optimization performed. ---")


if __name__ == "__main__":
    main()

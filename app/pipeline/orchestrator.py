"""The Phase 11 daily inference pipeline: ``run_daily_inference()``.

Orchestrates, without reimplementing, Phases 4-10:

    DATABASE -> FEATURE ENGINE -> XGBOOST + STATE ENGINE -> FUSION
    -> ALIGNMENT -> CONTRIBUTORS -> RECOMMENDATION -> DATABASE

Structure (see ``docs/daily_inference_pipeline.md`` "Transaction
boundary"): READ everything -> COMPUTE everything (feature engine,
model inference, state, fusion, alignment, contributors,
recommendation) -> BEGIN one atomic write transaction -> COMMIT. No
expensive computation ever happens while a write transaction is open.

**Failure-handling policy** (see docs "Failure handling" for the full
rationale):

- Read failure due to bad/missing input (unknown participant, target-day
  leakage guard, etc.) -> ``FAILED`` at stage ``"read"``, message is a
  deliberately-authored ``ValueError`` and safe to surface to a client.
  Any other read-time failure (e.g. a DB-layer error) -> ``FAILED`` at
  stage ``"read_infrastructure"`` instead, whose message must be
  treated as unsafe to surface. Either way nothing is written.
- Feature-engine failure -> ``FAILED`` at stage ``"feature_engine"``,
  nothing is written.
- XGBoost failure alone -> caught and treated as "XGBoost unavailable
  this run"; fusion's own documented state-only fallback applies.
- State-engine failure -> ``FAILED`` at stage ``"state_engine"``,
  nothing is written.
- Fusion failure -> ``FAILED`` at stage ``"fusion"``, nothing is
  written.
- Alignment/contributor/recommendation failure -> ``FAILED``; a
  fused DLMO with no alignment score is never silently invented.
- Any persistence failure -> the transaction rolls back in full
  (``app.database.engine.session_scope``); status ``FAILED`` at stage
  ``"persistence"``.

Every stage above degrades to a reported ``FAILED`` result rather than
an unhandled exception escaping ``run_daily_inference`` -- the one
documented exception is XGBoost, which degrades further still (to
state-only fusion) rather than failing at all.
"""

from __future__ import annotations

import logging
import time
from datetime import date as date_cls
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import sessionmaker

from app.alignment.config import DEFAULT_ALIGNMENT_CONFIG
from app.alignment.db_adapter import build_alignment_inputs
from app.alignment.engine import compute_alignment
from app.contributors.config import DEFAULT_CONTRIBUTOR_CONFIG
from app.contributors.db_adapter import build_contributor_inputs
from app.contributors.engine import rank_contributors
from app.database.engine import session_scope
from app.database.models import ParticipantProfile
from app.fusion.config import DEFAULT_FUSION_CONFIG
from app.fusion.fuse import fuse
from app.features.feature_manifest import FEATURE_MANIFEST_VERSION
from app.pipeline.config import DEFAULT_PIPELINE_CONFIG, PipelineConfig
from app.pipeline.persistence import (
    get_or_create_training_run,
    supersede_existing_label,
    update_participant_state,
    write_alignment_and_contributors,
    write_circadian_label,
    write_recommendation,
)
from app.pipeline.quality import build_data_quality_input, insufficient_history_data_quality
from app.pipeline.read import ReadResult, get_latest_label_for_date, read_daily_inference_inputs
from app.pipeline.state_step import run_state_step
from app.pipeline.traits import build_participant_traits, build_previous_state
from app.pipeline.types import (
    FAILED,
    INSUFFICIENT_HISTORY,
    NO_PREDICTION,
    SUCCESS,
    DailyInferenceResult,
    ParticipantStateUpdate,
)
from app.pipeline.xgboost_step import build_feature_step, run_xgboost_step
from app.recommendations.config import DEFAULT_RECOMMENDATION_CONFIG
from app.recommendations.db_adapter import (
    build_behavioral_history,
    load_candidate_interventions,
    load_prior_primary,
    load_recent_compliance,
)
from app.recommendations.engine import select_recommendations
from app.recommendations.inputs import RecommendationInputs
from app.state.config import DEFAULT_STATE_ENGINE_CONFIG
from app.synthetic.time_utils import clock_time_to_hour

logger = logging.getLogger(__name__)

_DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[2] / "models"

# Statuses this pipeline itself writes to prediction_status (lowercased).
# A pre-existing row with some other status (e.g. Phase 3's synthetic
# "synthetic_ground_truth" seed rows) is training/reference data, not a
# prior run of *this* pipeline -- it must not short-circuit a real
# inference request, though it is still superseded like any other
# existing row once this pipeline does write its own result.
_PIPELINE_OWNED_STATUSES = {SUCCESS.lower(), INSUFFICIENT_HISTORY.lower(), NO_PREDICTION.lower()}


def _fail(participant_id: int, target_date: date_cls, stage: str, message: str, started_at: float) -> DailyInferenceResult:
    logger.error("Daily inference failed for participant=%s date=%s stage=%s message=%s", participant_id, target_date, stage, message)
    return DailyInferenceResult(
        participant_id=participant_id,
        target_date=target_date,
        status=FAILED,
        failure_stage=stage,
        failure_message=message,
        persistence_status="not_attempted",
        runtime_seconds=time.monotonic() - started_at,
    )


def _idempotent_result(existing, participant_id: int, target_date: date_cls, started_at: float) -> DailyInferenceResult:
    return DailyInferenceResult(
        participant_id=participant_id,
        target_date=target_date,
        status=existing.prediction_status.upper() if existing.prediction_status else SUCCESS,
        persistence_status="skipped",
        circadian_label_id=existing.id,
        idempotent_short_circuit=True,
        runtime_seconds=time.monotonic() - started_at,
        diagnostics={"note": "Existing is_latest result returned without recomputation; pass force_rerun=True to recompute."},
    )


def _build_provenance(config: PipelineConfig, feature_manifest_version: str, model_version: Optional[int]) -> dict:
    return {
        "pipeline_version": config.pipeline_config_version,
        "feature_manifest_version": feature_manifest_version,
        "model_version": model_version,
        "state_config_version": DEFAULT_STATE_ENGINE_CONFIG.state_config_version,
        "fusion_config_version": DEFAULT_FUSION_CONFIG.fusion_config_version,
        "alignment_config_version": DEFAULT_ALIGNMENT_CONFIG.alignment_config_version,
        "contributor_config_version": DEFAULT_CONTRIBUTOR_CONFIG.contributor_config_version,
        "recommendation_config_version": DEFAULT_RECOMMENDATION_CONFIG.recommendation_config_version,
    }


def run_daily_inference(
    participant_id: int,
    target_date: date_cls,
    session_factory: sessionmaker,
    config: PipelineConfig = DEFAULT_PIPELINE_CONFIG,
    models_dir: Optional[Path] = None,
    force_rerun: bool = False,
) -> DailyInferenceResult:
    started_at = time.monotonic()
    models_dir = Path(models_dir) if models_dir is not None else _DEFAULT_MODELS_DIR

    # --- idempotency short-circuit (read-only, no computation) ---
    read_session = session_factory()
    try:
        if not force_rerun:
            existing = get_latest_label_for_date(read_session, participant_id, target_date)
            if existing is not None and existing.prediction_status in _PIPELINE_OWNED_STATUSES:
                return _idempotent_result(existing, participant_id, target_date, started_at)

        # --- STEPS 1-3: READ ---
        try:
            read_result: ReadResult = read_daily_inference_inputs(read_session, participant_id, target_date, config)
        except ValueError as exc:
            # read.py raises ValueError only for deliberately-authored,
            # client-safe messages (unknown participant, target-day
            # leakage guard, etc.) -- safe to surface to the API caller.
            return _fail(participant_id, target_date, "read", str(exc), started_at)
        except Exception as exc:
            # Anything else here is an infrastructure failure (e.g. a
            # DB-layer error), whose message may contain raw
            # connection/query detail and must never reach a client --
            # kept on a distinct stage name so the API layer can tell
            # the two apart (see app/api/services/inference_service.py).
            return _fail(participant_id, target_date, "read_infrastructure", str(exc), started_at)

        # --- traits / previous state ---
        try:
            traits = build_participant_traits(read_result.profile, read_result.window_observations, config)
        except ValueError as exc:
            return _fail(participant_id, target_date, "traits", str(exc), started_at)

        previous_state = build_previous_state(read_result.profile)

        # --- STEP 8: state engine ---
        try:
            state_step = run_state_step(previous_state, read_result.window_observations, traits, target_date, DEFAULT_STATE_ENGINE_CONFIG)
        except Exception as exc:  # do not write partial results
            return _fail(participant_id, target_date, "state_engine", str(exc), started_at)

        # --- STEPS 4-7: feature engine + XGBoost ---
        feature_step = None
        xgb_result = None
        sufficient_history = read_result.history_days_available >= config.min_consecutive_history_days
        if sufficient_history:
            try:
                feature_step = build_feature_step(participant_id, target_date, read_session)
            except Exception as exc:  # feature-engine failure: do not write partial results
                return _fail(participant_id, target_date, "feature_engine", str(exc), started_at)

            try:
                xgb_result = run_xgboost_step(feature_step.feature_vector, models_dir, config)
            except Exception:
                logger.exception(
                    "XGBoost inference failed for participant=%s date=%s; falling back to state-only fusion",
                    participant_id, target_date,
                )
                xgb_result = None

        # --- STEP 9: fusion ---
        data_quality = (
            build_data_quality_input(feature_step.feature_vector, config)
            if feature_step is not None
            else insufficient_history_data_quality()
        )
        previous_fused_dlmo = (
            clock_time_to_hour(read_result.previous_label.fused_dlmo_time)
            if read_result.previous_label is not None and read_result.previous_label.fused_dlmo_time is not None
            else None
        )
        try:
            fusion_result = fuse(
                xgb_dlmo=xgb_result.xgb_dlmo_hour if xgb_result is not None else None,
                state_dlmo=state_step.new_state.current_dlmo_hour,
                previous_fused_dlmo=previous_fused_dlmo,
                data_quality=data_quality,
                config=DEFAULT_FUSION_CONFIG,
            )
        except Exception as exc:  # do not write partial results
            return _fail(participant_id, target_date, "fusion", str(exc), started_at)

        if not sufficient_history:
            pipeline_status = INSUFFICIENT_HISTORY
        elif not fusion_result.prediction_made or fusion_result.fused_final is None:
            pipeline_status = NO_PREDICTION
        else:
            pipeline_status = SUCCESS

        # --- STEPS 10-12: alignment, contributors, recommendation ---
        alignment_result = None
        contributor_result = None
        recommendation_result = None
        if fusion_result.fused_final is not None:
            try:
                most_recent_obs = read_result.window_observations[-1] if read_result.window_observations else None
                alignment_inputs = build_alignment_inputs(
                    fusion_result.fused_final,
                    list(read_result.window_observations),
                    most_recent_observation=most_recent_obs,
                    chronotype=read_result.profile.chronotype_category,
                )
                alignment_result = compute_alignment(alignment_inputs)

                contributor_inputs = build_contributor_inputs(
                    traits, alignment_result, list(read_result.window_observations), latest_observation=most_recent_obs
                )
                contributor_result = rank_contributors(contributor_inputs)

                catalogue = load_candidate_interventions(read_session)
                behavioral_history = build_behavioral_history(
                    list(read_result.window_observations), actual_sleep_onset_hour=alignment_inputs.most_recent_sleep_onset_hour
                )
                recent_compliance = load_recent_compliance(read_session, participant_id, target_date)
                prior_primary = load_prior_primary(read_session, participant_id, target_date)
                recommendation_inputs = RecommendationInputs(
                    fused_dlmo_hour=fusion_result.fused_final,
                    alignment_result=alignment_result,
                    contributor_result=contributor_result,
                    behavioral_history=behavioral_history,
                    candidate_interventions=catalogue,
                    participant_id=participant_id,
                    today=target_date,
                    recent_compliance_by_intervention=recent_compliance,
                    prior_primary=prior_primary,
                )
                recommendation_result = select_recommendations(recommendation_inputs)
            except Exception as exc:
                # Never silently invent an alignment score.
                return _fail(participant_id, target_date, "alignment_contributor_recommendation", str(exc), started_at)

        provenance = _build_provenance(
            config,
            feature_step.feature_manifest_version if feature_step is not None else FEATURE_MANIFEST_VERSION,
            xgb_result.model_version if xgb_result is not None else None,
        )

        new_current_dlmo = fusion_result.fused_final
        new_adapted_dlmo = state_step.new_state.adapted_dlmo_hour
        new_alignment_score = alignment_result.final_score if alignment_result is not None else None

    finally:
        read_session.close()

    # --- STEPS 13-14: ONE atomic write transaction ---
    circadian_label_id = None
    persistence_status = "not_attempted"
    try:
        with session_scope(session_factory) as write_session:
            profile = write_session.get(ParticipantProfile, participant_id)

            training_run_id = None
            if xgb_result is not None:
                training_run = get_or_create_training_run(
                    write_session, "xgboost_dlmo", str(xgb_result.model_version), xgb_result.model_metadata
                )
                training_run_id = training_run.id

            supersede_existing_label(write_session, participant_id, target_date)
            label = write_circadian_label(
                write_session,
                participant_id,
                target_date,
                pipeline_status.lower(),
                xgb_result,
                {"state_dlmo_hour": state_step.new_state.current_dlmo_hour},
                fusion_result,
                feature_step.feature_vector if feature_step is not None else None,
                training_run_id,
            )
            circadian_label_id = label.id

            if alignment_result is not None:
                write_alignment_and_contributors(
                    write_session, label, participant_id, target_date, alignment_result, contributor_result, provenance
                )
            write_recommendation(write_session, participant_id, target_date, recommendation_result)

            previous_current = clock_time_to_hour(profile.current_dlmo_time) if profile.current_dlmo_time else None
            previous_adapted = clock_time_to_hour(profile.adapted_dlmo_time) if profile.adapted_dlmo_time else None
            update_participant_state(write_session, profile, target_date, new_current_dlmo, new_adapted_dlmo, new_alignment_score)

        persistence_status = "committed"
    except Exception as exc:
        return _fail(participant_id, target_date, "persistence", str(exc), started_at)

    state_update = ParticipantStateUpdate(
        previous_current_dlmo_hour=previous_current,
        new_current_dlmo_hour=new_current_dlmo,
        previous_adapted_dlmo_hour=previous_adapted,
        new_adapted_dlmo_hour=new_adapted_dlmo,
        intrinsic_dlmo_hour_unchanged=traits.intrinsic_dlmo_hour,
        new_alignment_score=new_alignment_score,
        applied=True,
    )

    return DailyInferenceResult(
        participant_id=participant_id,
        target_date=target_date,
        status=pipeline_status,
        history_days_available=read_result.history_days_available,
        feature_metadata=(
            {
                "completeness": feature_step.feature_vector.completeness,
                "missing_features": list(feature_step.feature_vector.missing_features),
                "imputed_features": list(feature_step.feature_vector.imputed_features),
            }
            if feature_step is not None
            else None
        ),
        xgb_prediction=(
            {"xgb_dlmo_hour": xgb_result.xgb_dlmo_hour, "model_version": xgb_result.model_version}
            if xgb_result is not None
            else None
        ),
        state_prediction={
            "state_dlmo_hour": state_step.new_state.current_dlmo_hour,
            "was_initialized": state_step.was_initialized,
            "was_updated": state_step.was_updated,
            "reason": state_step.reason,
        },
        fusion_result=fusion_result,
        alignment_result=alignment_result,
        contributor_result=contributor_result,
        recommendation_result=recommendation_result,
        participant_state_update=state_update,
        persistence_status=persistence_status,
        circadian_label_id=circadian_label_id,
        runtime_seconds=time.monotonic() - started_at,
        diagnostics={"provenance": provenance},
    )

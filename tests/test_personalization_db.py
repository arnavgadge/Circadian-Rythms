"""Database-integration tests for Phase 13 personalization: controlled
synthetic harnesses (reusing the Phase 12 harness pattern) that inject
known intervention histories, then verify graduation, ranking, the
personalized-recommendation output, temporal-leakage prevention, and
the update pipeline's database persistence.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.database.models import (
    AlignmentResult,
    CircadianLabel,
    DailyObservation,
    InterventionLog,
    Participant,
    ParticipantProfile,
    PersonalEffectModel,
    Recommendation,
)
from app.personalization.config import DEFAULT_PERSONALIZATION_CONFIG, PersonalizationConfig
from app.personalization.db_adapter import count_compliance_observations, weeks_active_for_type
from app.personalization.dispatcher import get_personalization_phase, personalize_recommendations
from app.personalization.ranking import compute_personal_ranking_entry
from app.personalization.update import UPDATED, update_personalization_state
from app.recommendations.catalogue import intervention_from_recommendation
from app.recommendations.personalization import LITERATURE, PERSONAL_EFFECT
from app.synthetic.time_utils import hour_to_clock_time, normalize_hour

_TYPE_METADATA = {
    "screen": {
        "contributor_signals": ["evening_screen"], "value_kind": "clock_hour", "direction": "earlier",
        "template": "Try stopping screens by {target_time}.", "desired_value_assumption": -0.5,
        "desired_value_relative_to": "ideal_sleep_onset", "max_shift_per_recommendation": 1.5,
        "baseline_feasibility": 0.5, "is_literature_verified": False,
    },
    "light": {
        "contributor_signals": ["morning_light"], "value_kind": "duration_minutes", "direction": "increase",
        "template": "Try getting {target_value} of light.", "desired_value_assumption": 30.0,
        "desired_value_relative_to": None, "max_shift_per_recommendation": 15.0,
        "baseline_feasibility": 0.65, "is_literature_verified": False,
    },
    "meal": {
        "contributor_signals": ["meal_timing"], "value_kind": "clock_hour", "direction": "earlier",
        "template": "Try finishing your last meal by {target_time}.", "desired_value_assumption": -3.0,
        "desired_value_relative_to": "ideal_sleep_onset", "max_shift_per_recommendation": 1.0,
        "baseline_feasibility": 0.6, "is_literature_verified": False,
    },
    # Social-jetlag reduction: unlike morning_light/meal_timing/exercise,
    # this signal is NOT one of Phase 12's Phase 3 regression covariates
    # (only morning_light/meal_timing/exercise are), so using it as the
    # comparison arm in these scenario tests avoids the collinearity
    # between "compliance to this signal's own target" and "this
    # signal's own value as a covariate" that a self-referential target
    # (e.g. morning_light) would otherwise introduce into Phase 12's
    # regression -- a real, documented characteristic of Phase 12's
    # locked covariate set, not something this phase alters.
    "sleep": {
        "contributor_signals": ["social_jetlag"], "value_kind": "duration_minutes", "direction": "decrease",
        "template": "Try keeping your schedule consistent to within {target_value}.", "desired_value_assumption": 0.0,
        "desired_value_relative_to": None, "max_shift_per_recommendation": 30.0,
        "baseline_feasibility": 0.55, "is_literature_verified": False,
    },
}


def _make_participant(session, code: str) -> Participant:
    participant = Participant(participant_code=code, enrollment_date=date(2026, 1, 1), status="active")
    session.add(participant)
    session.flush()
    session.add(
        ParticipantProfile(
            participant_id=participant.id, chronotype_category="Intermediate",
            intrinsic_dlmo_time=hour_to_clock_time(21.0), adapted_dlmo_time=hour_to_clock_time(21.0),
            current_dlmo_time=hour_to_clock_time(21.0),
        )
    )
    return participant


def _make_recommendation(session, intervention_type: str, code: str, literature_minutes: float = 15.0) -> Recommendation:
    rec = Recommendation(
        intervention_code=code, intervention_type=intervention_type, title=f"Test {intervention_type}",
        target_behavior=f"{intervention_type}_behavior", literature_expected_improvement_minutes=literature_minutes,
        source="test fixture", extra_metadata=_TYPE_METADATA[intervention_type],
    )
    session.add(rec)
    session.flush()
    return rec


def _inject_intervention_history(
    session, participant: Participant, recommendation: Recommendation, intervention_type: str,
    start_date: date, n_days: int, true_effect: float, compliance_fn, dlmo_start: float = 21.0,
    baseline_days: int = 7,
) -> float:
    """Writes ``baseline_days`` of pre-intervention baseline
    observations (flat DLMO, no ``intervention_log`` row -- Phase 12's
    before/after analysis needs a real baseline window to exist) plus
    ``n_days`` of DailyObservation/CircadianLabel/AlignmentResult/
    InterventionLog rows starting at ``start_date``, with a known,
    noise-free compliance -> DLMO-change relationship. Returns the
    final DLMO hour reached (so a caller can chain a second
    intervention's history starting from where this one left off)."""

    dlmo = dlmo_start
    for i in range(baseline_days, 0, -1):
        d = start_date - timedelta(days=i)
        session.add(
            DailyObservation(
                participant_id=participant.id, observation_date=d, sleep_onset_time=hour_to_clock_time(dlmo + 2.0),
                morning_light_duration_minutes=20.0, evening_screen_duration_minutes=3.0 * 60.0,
                last_meal_time=hour_to_clock_time(22.0), exercise_time=hour_to_clock_time(18.0),
                last_caffeine_time=hour_to_clock_time(10.0), caffeine_amount_mg=0.0,
            )
        )
        session.flush()
        label = CircadianLabel(
            participant_id=participant.id, target_date=d, is_latest=True, prediction_status="success",
            fused_dlmo_time=hour_to_clock_time(dlmo), data_completeness=1.0,
        )
        session.add(label)
        session.flush()
        session.add(
            AlignmentResult(
                circadian_label_id=label.id, participant_id=participant.id, target_date=d,
                final_alignment_score=60.0, phase_alignment_score=60.0, behavioral_alignment_score=60.0,
            )
        )

    for i in range(n_days):
        d = start_date + timedelta(days=i)
        compliance = compliance_fn(i)
        dlmo = normalize_hour(dlmo + (true_effect * compliance) / 60.0)

        kwargs = dict(
            participant_id=participant.id, observation_date=d, sleep_onset_time=hour_to_clock_time(dlmo + 2.0),
            morning_light_duration_minutes=20.0, evening_screen_duration_minutes=3.0 * 60.0,
            last_meal_time=hour_to_clock_time(22.0), exercise_time=hour_to_clock_time(18.0),
            last_caffeine_time=hour_to_clock_time(10.0), caffeine_amount_mg=0.0,
        )
        if intervention_type == "screen":
            kwargs["evening_screen_duration_minutes"] = (1.0 - compliance) * 3.0 * 60.0 + 0.1
        elif intervention_type == "light":
            kwargs["morning_light_duration_minutes"] = 10.0 + compliance * 40.0
        elif intervention_type == "meal":
            kwargs["last_meal_time"] = hour_to_clock_time(22.5 - compliance * 1.5)
        elif intervention_type == "sleep":
            kwargs["social_jetlag_minutes"] = (1.0 - compliance) * 60.0 + 0.1

        session.add(DailyObservation(**kwargs))
        session.flush()

        label = CircadianLabel(
            participant_id=participant.id, target_date=d, is_latest=True, prediction_status="success",
            fused_dlmo_time=hour_to_clock_time(dlmo), data_completeness=1.0,
        )
        session.add(label)
        session.flush()
        session.add(
            AlignmentResult(
                circadian_label_id=label.id, participant_id=participant.id, target_date=d,
                final_alignment_score=60.0 + i * 0.3, phase_alignment_score=60.0, behavioral_alignment_score=60.0,
            )
        )
        session.add(
            InterventionLog(
                participant_id=participant.id, recommendation_id=recommendation.id, log_date=d,
                recommendation_text="test", target_value_time=hour_to_clock_time(21.5),
                compliance_degree=compliance, compliance_binary=compliance >= 0.65,
                expected_improvement_minutes=15.0, personalization_phase="literature",
            )
        )

    session.commit()
    return dlmo


def _cycle_compliance(i: int) -> float:
    return ((i % 10) / 10.0)


# --- 13 & 14. Intervention-specific personalization / independent graduation ---


def test_independent_graduation_across_intervention_types(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "PERS-001")
    screen_rec = _make_recommendation(session, "screen", "PERS_SCREEN_001")
    light_rec = _make_recommendation(session, "light", "PERS_LIGHT_001")
    session.commit()

    # Screen: long exposure (35 days, ~5 weeks) -> should reach PERSONAL_EFFECT.
    _inject_intervention_history(session, participant, screen_rec, "screen", date(2026, 1, 1), 35, -10.0, _cycle_compliance)
    # Light: short exposure (5 days) -> should stay at LITERATURE.
    _inject_intervention_history(session, participant, light_rec, "light", date(2026, 3, 1), 5, 8.0, _cycle_compliance)

    as_of = date(2026, 3, 10)
    screen_phase = get_personalization_phase(session, participant.id, "screen", as_of)
    light_phase = get_personalization_phase(session, participant.id, "light", as_of)

    assert screen_phase == PERSONAL_EFFECT
    assert light_phase == LITERATURE
    assert screen_phase != light_phase  # never one global phase for the whole participant


# --- 15 & 16. Temporal leakage prevention / future-data exclusion ---


def test_evidence_gathering_never_sees_future_observations(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "PERS-002")
    rec = _make_recommendation(session, "screen", "PERS_SCREEN_002")
    session.commit()

    _inject_intervention_history(session, participant, rec, "screen", date(2026, 1, 1), 40, -10.0, _cycle_compliance)

    cutoff = date(2026, 1, 15)  # only the first 14 days should be visible
    n_before_cutoff = count_compliance_observations(session, participant.id, "screen", cutoff)
    n_full_history = count_compliance_observations(session, participant.id, "screen", date(2026, 2, 20))

    assert n_before_cutoff == 14
    assert n_full_history == 40
    assert n_before_cutoff < n_full_history  # the later call legitimately sees more; the earlier one must not


def test_recommendation_on_day_31_cannot_see_day_32_outcomes(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "PERS-003")
    rec = _make_recommendation(session, "screen", "PERS_SCREEN_003")
    session.commit()

    start = date(2026, 1, 1)
    _inject_intervention_history(session, participant, rec, "screen", start, 40, -10.0, _cycle_compliance)

    day_31 = start + timedelta(days=30)
    n_as_of_day_31 = count_compliance_observations(session, participant.id, "screen", day_31)
    # Day 31 evidence must only include days strictly before day 31 (days 0..29 = 30 days).
    assert n_as_of_day_31 == 30


# --- 18. Recommendation-engine integration contract ---


def test_personalize_recommendations_output_feeds_recommendation_inputs_directly(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "PERS-004")
    screen_rec = _make_recommendation(session, "screen", "PERS_SCREEN_004")
    session.commit()
    _inject_intervention_history(session, participant, screen_rec, "screen", date(2026, 1, 1), 35, -10.0, _cycle_compliance)

    as_of = date(2026, 2, 10)
    catalogue = [intervention_from_recommendation(screen_rec)]
    output = personalize_recommendations(session, participant.id, catalogue, as_of)

    assert output.effective_personalization_phase in (LITERATURE, "personal_ranking", PERSONAL_EFFECT)
    # The dicts are keyed exactly by intervention_id, as RecommendationInputs expects.
    for intervention_id in output.personal_expected_improvement:
        assert intervention_id == screen_rec.id
    for intervention_id in output.personalized_ranking:
        assert intervention_id == screen_rec.id


# --- 23. Posterior persistence / 30. database persistence / 31. model-version auditability ---


def test_update_pipeline_persists_personal_effect_model(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "PERS-005")
    rec = _make_recommendation(session, "screen", "PERS_SCREEN_005")
    session.commit()
    _inject_intervention_history(session, participant, rec, "screen", date(2026, 1, 1), 35, -10.0, _cycle_compliance)

    outcome = update_personalization_state(session, participant.id, "screen", date(2026, 2, 10))
    assert outcome.status == UPDATED
    assert outcome.personal_effect_model is not None
    assert outcome.personal_effect_model.model_version == DEFAULT_PERSONALIZATION_CONFIG.personalization_config_version

    stored = session.execute(
        select(PersonalEffectModel).where(
            PersonalEffectModel.participant_id == participant.id, PersonalEffectModel.intervention_type == "screen"
        )
    ).scalars().one()
    assert stored.slope == pytest.approx(-10.0, abs=1.0)
    assert stored.num_observations > 0
    assert stored.evidence_source == "phase3_regression"

    from app.database.models import InterventionEffectEstimate

    history_rows = session.execute(
        select(InterventionEffectEstimate).where(InterventionEffectEstimate.participant_id == participant.id)
    ).scalars().all()
    assert len(history_rows) >= 1  # Phase 12's auditable log recorded the evaluation this update triggered


# --- 27 & 28. Synthetic personalization scenarios A and B ---


def test_synthetic_scenario_a_favors_strong_effect_intervention(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "PERS-A")
    sleep_rec = _make_recommendation(session, "sleep", "PERS_A_SLEEP")
    screen_rec = _make_recommendation(session, "screen", "PERS_A_SCREEN")
    session.commit()

    # Both interventions get identical, ample, equally-compliant exposure --
    # only the true effect magnitude differs.
    _inject_intervention_history(session, participant, sleep_rec, "sleep", date(2026, 1, 1), 30, true_effect=15.0, compliance_fn=_cycle_compliance)
    _inject_intervention_history(session, participant, screen_rec, "screen", date(2026, 2, 15), 30, true_effect=3.0, compliance_fn=_cycle_compliance)

    as_of = date(2026, 3, 10)
    update_personalization_state(session, participant.id, "sleep", as_of)
    update_personalization_state(session, participant.id, "screen", as_of)

    sleep_entry = compute_personal_ranking_entry(
        "sleep", 15.0, 3,
        _latest_effect_value(session, participant.id, "sleep", as_of),
        count_compliance_observations(session, participant.id, "sleep", as_of),
        _compliance_values(session, participant.id, "sleep", as_of),
    )
    screen_entry = compute_personal_ranking_entry(
        "screen", 15.0, 3,
        _latest_effect_value(session, participant.id, "screen", as_of),
        count_compliance_observations(session, participant.id, "screen", as_of),
        _compliance_values(session, participant.id, "screen", as_of),
    )

    assert sleep_entry.personal_score > screen_entry.personal_score  # stronger true effect -> favored


def test_synthetic_scenario_b_accounts_for_both_effect_and_compliance(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "PERS-B")
    screen_rec = _make_recommendation(session, "screen", "PERS_B_SCREEN")  # high compliance, moderate effect
    sleep_rec = _make_recommendation(session, "sleep", "PERS_B_SLEEP")     # low compliance, strong effect
    session.commit()

    _inject_intervention_history(session, participant, screen_rec, "screen", date(2026, 1, 1), 30, true_effect=6.0, compliance_fn=lambda i: 0.85 + 0.1 * ((i % 3) / 2.0))
    _inject_intervention_history(session, participant, sleep_rec, "sleep", date(2026, 2, 15), 30, true_effect=20.0, compliance_fn=lambda i: 0.15 + 0.1 * ((i % 3) / 2.0))

    as_of = date(2026, 3, 10)
    update_personalization_state(session, participant.id, "screen", as_of)
    update_personalization_state(session, participant.id, "sleep", as_of)

    screen_entry = compute_personal_ranking_entry(
        "screen", 15.0, 3, _latest_effect_value(session, participant.id, "screen", as_of),
        count_compliance_observations(session, participant.id, "screen", as_of), _compliance_values(session, participant.id, "screen", as_of),
    )
    sleep_entry = compute_personal_ranking_entry(
        "sleep", 15.0, 3, _latest_effect_value(session, participant.id, "sleep", as_of),
        count_compliance_observations(session, participant.id, "sleep", as_of), _compliance_values(session, participant.id, "sleep", as_of),
    )

    # Both compliance AND effect are reflected -- neither dimension alone determines the score.
    assert screen_entry.compliance_probability > sleep_entry.compliance_probability
    assert sleep_entry.personal_effect > screen_entry.personal_effect
    # The score is the product of both, not either alone.
    assert screen_entry.personal_score == pytest.approx(abs(screen_entry.personal_effect) * screen_entry.compliance_probability)
    assert sleep_entry.personal_score == pytest.approx(abs(sleep_entry.personal_effect) * sleep_entry.compliance_probability)


def _latest_effect_value(session, participant_id, intervention_type, as_of_date):
    from app.personalization.db_adapter import latest_effect_estimate

    row = latest_effect_estimate(session, participant_id, intervention_type, as_of_date)
    return row.effect_estimate if row is not None else None


def _compliance_values(session, participant_id, intervention_type, as_of_date):
    from app.personalization.db_adapter import historical_compliance_values

    return historical_compliance_values(session, participant_id, intervention_type, as_of_date)


# A complementary check on scenario A: the stronger true effect must
# also be recovered correctly in the *persisted* personal_effect_models
# row (not just the in-memory ranking entry above).


def test_synthetic_scenario_a_persisted_model_recovers_stronger_effect(db_session_factory):
    session = db_session_factory()
    participant = _make_participant(session, "PERS-A2")
    sleep_rec = _make_recommendation(session, "sleep", "PERS_A2_SLEEP")
    screen_rec = _make_recommendation(session, "screen", "PERS_A2_SCREEN")
    session.commit()

    _inject_intervention_history(session, participant, sleep_rec, "sleep", date(2026, 1, 1), 30, true_effect=15.0, compliance_fn=_cycle_compliance)
    _inject_intervention_history(session, participant, screen_rec, "screen", date(2026, 2, 15), 30, true_effect=3.0, compliance_fn=_cycle_compliance)

    as_of = date(2026, 3, 10)
    update_personalization_state(session, participant.id, "sleep", as_of)
    update_personalization_state(session, participant.id, "screen", as_of)

    sleep_model = session.execute(
        select(PersonalEffectModel).where(PersonalEffectModel.participant_id == participant.id, PersonalEffectModel.intervention_type == "sleep")
    ).scalars().one()
    screen_model = session.execute(
        select(PersonalEffectModel).where(PersonalEffectModel.participant_id == participant.id, PersonalEffectModel.intervention_type == "screen")
    ).scalars().one()

    assert abs(sleep_model.slope) > abs(screen_model.slope)  # the stronger true effect is recovered as stronger

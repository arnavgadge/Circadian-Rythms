"""AUDIT 11 -- Recommendation engine adversarial checks.

Targets: 1-primary/<=2-supporting at the backend layer (not the UI's
.slice(0,2) safety net), graduated-target circular arithmetic across
midnight, boundary/clamping behavior, deterministic conflict
resolution, repetition behavior over many days (documented as
architecturally fine -- no fatigue logic exists), low-feasibility
graduation, and a scan of the seeded catalogue for medical language.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.alignment.engine import compute_alignment
from app.alignment.inputs import AlignmentInputs
from app.contributors.engine import rank_contributors
from app.contributors.inputs import ContributorInputs
from app.database.seed import _REFERENCE_RECOMMENDATIONS
from app.recommendations.behavior import BehavioralHistory
from app.recommendations.catalogue import CLOCK_HOUR, DECREASE, DURATION_MINUTES, EARLIER, INCREASE, CandidateIntervention
from app.recommendations.config import DEFAULT_RECOMMENDATION_CONFIG
from app.recommendations.cooldown import PriorPrimary
from app.recommendations.engine import select_recommendations
from app.recommendations.inputs import RecommendationInputs
from app.recommendations.targets import compute_graduated_target
from app.safety.messages import PROHIBITED_RECOMMENDATION_TERMS
from app.state.circadian_state import ParticipantPhaseTraits


def _traits(**overrides) -> ParticipantPhaseTraits:
    defaults = dict(
        intrinsic_dlmo_hour=21.0, baseline_sleep_onset_hour=23.0,
        light_sensitivity=1.0, screen_sensitivity=1.0, meal_sensitivity=1.0, chronotype="Intermediate",
    )
    defaults.update(overrides)
    return ParticipantPhaseTraits(**defaults)


def _alignment_result(**overrides):
    defaults = dict(
        fused_dlmo_hour=21.75,
        most_recent_sleep_onset_hour=23.9,
        window_sleep_onset_hours=[23.7, 23.8, 23.9, 23.75, 23.85, 23.9],
        window_morning_light_duration_minutes=[10, 8, 12, 9, 11, 10],
        window_evening_screen_duration_hours=[3.5, 4.0, 3.8, 4.2, 3.9, 4.1],
        window_last_meal_hours=[21.5, 22.0, 21.8, 22.2, 21.9, 22.1],
        window_social_jetlag_minutes=[None, None, None, None, 90.0, None],
        chronotype="Intermediate",
    )
    defaults.update(overrides)
    return compute_alignment(AlignmentInputs(**defaults))


def _contributor_result(alignment_result=None, **overrides):
    alignment_result = alignment_result or _alignment_result()
    defaults = dict(
        traits=_traits(),
        alignment_result=alignment_result,
        window_morning_light_duration_minutes=[10, 8, 12, 9, 11, 10],
        window_evening_screen_duration_hours=[3.5, 4.0, 3.8, 4.2, 3.9, 4.1],
        window_last_meal_hours=[21.5, 22.0, 21.8, 22.2, 21.9, 22.1],
        window_exercise_hours=[19.0, 19.5, 18.5, 19.2, 19.1, 18.8],
        window_social_jetlag_minutes=[None, None, None, None, 90.0, None],
        latest_morning_light_duration_minutes=10.0,
        latest_evening_screen_duration_hours=4.0,
        latest_last_meal_hour=22.0,
        latest_exercise_hour=19.0,
        latest_social_jetlag_minutes=90.0,
    )
    defaults.update(overrides)
    return rank_contributors(ContributorInputs(**defaults))


def _behavioral_history(**overrides) -> BehavioralHistory:
    defaults = dict(
        actual_sleep_onset_hour=23.9,
        window_evening_screen_duration_hours=[3.5, 4.0, 3.8, 4.2, 3.9, 4.1],
        window_morning_light_duration_minutes=[10, 8, 12, 9, 11, 10],
        window_last_meal_hours=[21.5, 22.0, 21.8, 22.2, 21.9, 22.1],
        window_exercise_hours=[19.0, 19.5, 18.5, 19.2, 19.1, 18.8],
        window_social_jetlag_minutes=[None, None, None, None, 90.0, None],
    )
    defaults.update(overrides)
    return BehavioralHistory(**defaults)


def _candidate(**overrides) -> CandidateIntervention:
    defaults = dict(
        intervention_id=1, intervention_code="TEST_SCREEN", intervention_type="screen", title="Test screen",
        is_active=True, contributor_signals=("evening_screen",), value_kind=CLOCK_HOUR, direction=EARLIER,
        template="Try stopping screens by {target_time}.",
        desired_value_assumption=-0.5, desired_value_relative_to="ideal_sleep_onset",
        max_shift_per_recommendation=1.5, min_target_value=None, max_target_value=None,
        baseline_feasibility=0.6, severity_applicability=(), literature_expected_improvement_minutes=15.0,
        is_literature_verified=False, source_note="test",
    )
    defaults.update(overrides)
    return CandidateIntervention(**defaults)


def _inputs(candidates, **overrides) -> RecommendationInputs:
    defaults = dict(
        fused_dlmo_hour=21.75,
        alignment_result=_alignment_result(),
        contributor_result=_contributor_result(),
        behavioral_history=_behavioral_history(),
        candidate_interventions=tuple(candidates),
        recent_compliance_by_intervention={},
        personalization_phase="literature",
        personalized_ranking={},
        personal_expected_improvement={},
        prior_primary=None,
        today=date(2026, 1, 15),
    )
    defaults.update(overrides)
    return RecommendationInputs(**defaults)


# --- 1 primary + <=2 supporting, at the backend layer ---


def test_never_more_than_one_primary_and_two_supporting_with_many_candidates():
    """Five candidates all matching the top contributor -- if the
    backend guarantee were absent, a naive engine might return every
    matching candidate as an equally-weighted recommendation. Confirm
    the RecommendationResult itself (not any UI truncation) caps at
    1 + 2."""

    candidates = [
        _candidate(intervention_id=i, intervention_code=f"C{i}", contributor_signals=("evening_screen",))
        for i in range(1, 6)
    ]
    result = select_recommendations(_inputs(candidates))
    assert result.primary is not None
    assert len(result.supporting) <= 2
    all_ids = [result.primary.intervention_id] + [s.intervention_id for s in result.supporting]
    assert len(all_ids) <= 3
    assert len(set(all_ids)) == len(all_ids)  # no duplicate intervention appears twice


# --- Graduated target: circular midnight arithmetic ---


def test_graduated_target_crossing_midnight_uses_circular_arithmetic():
    """Docs worked example: current cutoff 01:30, desired 22:30. A naive
    linear (desired - current) would compute +21h; the correct circular
    shortest-path shift is -3h, landing the 50%-graduated target at
    00:00 -- never at some nonsensical 11-hour-away clock time."""

    candidate = _candidate(desired_value_relative_to=None, desired_value_assumption=22.5, max_shift_per_recommendation=12.0)
    target = compute_graduated_target(candidate, current_value=1.5, ideal_sleep_onset_hour=None, fraction=0.5)

    assert target.raw_gap == pytest.approx(-3.0)
    assert target.applied_shift == pytest.approx(-1.5)
    assert target.target_value == pytest.approx(0.0, abs=1e-9)
    assert 0.0 <= target.target_value < 24.0


@pytest.mark.parametrize("current,desired", [(23.95, 0.05), (0.05, 23.95), (0.0, 0.0), (23.99, 0.0)])
def test_graduated_target_near_midnight_boundary_always_lands_on_sane_clock_time(current, desired):
    """Boundary construction near the 24h wrap point must never produce
    a target outside [0, 24) or NaN, regardless of which side of
    midnight current/desired fall on."""

    candidate = _candidate(desired_value_relative_to=None, desired_value_assumption=desired, max_shift_per_recommendation=12.0)
    target = compute_graduated_target(candidate, current_value=current, ideal_sleep_onset_hour=None, fraction=0.5)
    assert 0.0 <= target.target_value < 24.0
    assert target.target_value == target.target_value  # not NaN


def test_graduated_target_shift_beyond_bound_is_clamped_not_malformed():
    """A candidate whose max_shift_per_recommendation is much smaller
    than the theoretical gap must clip the shift, never silently
    exceed the bound or wrap to a nonsensical value."""

    candidate = _candidate(
        value_kind=DURATION_MINUTES, direction=INCREASE, desired_value_relative_to=None,
        desired_value_assumption=180.0, max_shift_per_recommendation=5.0, min_target_value=0.0, max_target_value=300.0,
    )
    target = compute_graduated_target(candidate, current_value=0.0, ideal_sleep_onset_hour=None, fraction=0.5)
    assert target.bound_clipped is True
    assert abs(target.applied_shift) <= 5.0 + 1e-9
    assert 0.0 <= target.target_value <= 300.0
    assert target.target_value < target.desired_value  # far short of the full theoretical jump


def test_wrong_direction_current_already_past_target_is_clamped_to_zero_shift():
    """Current behavior already earlier than the desired direction ->
    never recommend moving backwards to 'catch up'."""

    # direction=EARLIER, desired 22:00, but current is already 20:00 (earlier than desired).
    candidate = _candidate(desired_value_relative_to=None, desired_value_assumption=22.0, direction=EARLIER)
    target = compute_graduated_target(candidate, current_value=20.0, ideal_sleep_onset_hour=None, fraction=0.5)
    assert target.wrong_direction_clamped is True
    assert target.applied_shift == pytest.approx(0.0)
    assert target.target_value == pytest.approx(20.0)


# --- Low-feasibility (huge single-day jump) still graduates ---


def test_low_feasibility_huge_gap_still_only_moves_halfway_not_full_jump():
    """An intervention with a very large theoretical gap (e.g. desired
    value far from current) must still only move `graduated_target_fraction`
    of the way -- never prescribe the full jump in one step, regardless
    of how large or 'urgent' the gap looks."""

    candidate = _candidate(
        value_kind=DURATION_MINUTES, direction=INCREASE, desired_value_relative_to=None,
        desired_value_assumption=180.0, max_shift_per_recommendation=1000.0, min_target_value=0.0, max_target_value=300.0,
    )
    target = compute_graduated_target(candidate, current_value=0.0, ideal_sleep_onset_hour=None, fraction=0.5)
    assert target.target_value == pytest.approx(90.0)  # halfway to 180, not the full 180
    assert target.target_value < candidate.desired_value_assumption


# --- Conflicting recommendations resolved deterministically ---


def test_conflicting_candidates_resolve_to_one_deterministic_primary():
    """Two candidates that both plausibly address the same top
    contributor with equal scoring inputs -- the engine must still pick
    exactly one deterministic primary (never both, never nondeterministically)."""

    c1 = _candidate(intervention_id=10, intervention_code="A", contributor_signals=("evening_screen",))
    c2 = _candidate(intervention_id=11, intervention_code="B", contributor_signals=("evening_screen",))

    results = [select_recommendations(_inputs([c1, c2])) for _ in range(5)]
    primaries = {r.primary.intervention_id for r in results}
    assert len(primaries) == 1  # same candidate wins every run, not flip-flopping


# --- Repetition over many days: no fatigue logic; architecturally fine to repeat ---


def test_same_primary_recommendation_may_repeat_indefinitely_with_stable_inputs():
    """With a completely stable scenario across many simulated days (no
    change in contributors/history), the same intervention is selected
    as primary every day. This is a documented architectural choice
    (docs/recommendation_engine.md section 11: 'a simple adherence
    heuristic', not a repetition-fatigue system) -- pinned here as a
    regression test of that documented behavior, not treated as a bug."""

    candidate = _candidate()
    other = _candidate(intervention_id=2, intervention_code="OTHER", contributor_signals=("meal_timing",))

    prior = None
    chosen_ids = []
    base_day = date(2026, 1, 1)
    for day_offset in range(10):
        today = base_day + timedelta(days=day_offset)
        result = select_recommendations(_inputs([candidate, other], prior_primary=prior, today=today))
        chosen_ids.append(result.primary.intervention_id)
        prior = PriorPrimary(intervention_id=result.primary.intervention_id, log_date=today)

    assert chosen_ids == [candidate.intervention_id] * 10  # repeats every day; no forced rotation exists


# --- No medical recommendations anywhere in the real seeded catalogue ---


def test_seeded_catalogue_contains_no_medical_or_medication_language():
    banned = PROHIBITED_RECOMMENDATION_TERMS
    for entry in _REFERENCE_RECOMMENDATIONS:
        haystack = " ".join(
            str(v) for v in (
                entry.get("title", ""), entry.get("description", ""),
                (entry.get("extra_metadata") or {}).get("template", ""),
            )
        ).lower()
        for term in banned:
            assert term not in haystack, f"{entry['intervention_code']} contains banned term {term!r}"

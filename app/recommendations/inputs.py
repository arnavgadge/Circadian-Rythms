"""Input and cross-cutting types for the recommendation engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls
from typing import Optional, Sequence

from app.alignment.engine import AlignmentResult
from app.contributors.engine import ContributorResult
from app.recommendations.behavior import BehavioralHistory
from app.recommendations.catalogue import CandidateIntervention
from app.recommendations.cooldown import PriorPrimary
from app.recommendations.feasibility import RecentComplianceRecord
from app.recommendations.personalization import LITERATURE


@dataclass(frozen=True)
class RecommendationInputs:
    """Everything :func:`app.recommendations.engine.select_recommendations`
    needs. Conceptually mirrors the ``select_recommendations(...)`` call
    shape from the Phase 10 brief."""

    fused_dlmo_hour: float
    alignment_result: AlignmentResult
    contributor_result: ContributorResult
    behavioral_history: BehavioralHistory
    candidate_interventions: Sequence[CandidateIntervention]

    participant_id: Optional[int] = None
    today: Optional[date_cls] = None

    personalization_phase: str = LITERATURE
    personalized_ranking: Optional[dict] = None
    personal_expected_improvement: Optional[dict] = None

    # intervention_id -> recent compliance records within the lookback window
    recent_compliance_by_intervention: dict = field(default_factory=dict)
    prior_primary: Optional[PriorPrimary] = None

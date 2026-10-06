"""SQLAlchemy ORM models for the CircadianIQ relational schema.

Importing this package registers every model on ``Base.metadata``,
which is required before ``Base.metadata.create_all()`` or Alembic
autogenerate can see the full schema. See
``docs/database_architecture.md`` for the full design rationale.
"""

from app.database.models.base import Base, CreatedAtMixin, PortableJSON, TimestampMixin
from app.database.models.circadian import AlignmentResult, CircadianLabel, ContributorResult
from app.database.models.effectiveness import InterventionEffectEstimate
from app.database.models.observations import DailyObservation, PhysiologyLog
from app.database.models.participant import Participant, ParticipantProfile
from app.database.models.personalization import BanditState, PersonalEffectModel
from app.database.models.quality import MissingDataEvent
from app.database.models.recommendations import InterventionLog, Recommendation
from app.database.models.safety import SafetyFlag
from app.database.models.training import TrainingRun

__all__ = [
    "Base",
    "CreatedAtMixin",
    "TimestampMixin",
    "PortableJSON",
    "Participant",
    "ParticipantProfile",
    "DailyObservation",
    "PhysiologyLog",
    "CircadianLabel",
    "AlignmentResult",
    "ContributorResult",
    "Recommendation",
    "InterventionLog",
    "PersonalEffectModel",
    "BanditState",
    "MissingDataEvent",
    "SafetyFlag",
    "TrainingRun",
    "InterventionEffectEstimate",
]

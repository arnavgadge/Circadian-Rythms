"""safety layer metadata (Phase 14)

Revision ID: c3f7a08e21b4
Revises: bd2e1f4a9c31
Create Date: 2026-09-09 00:00:00.000000

Purely additive: five nullable columns on the existing ``safety_flags``
table, plus three nullable columns on ``circadian_labels`` so a safety
decision can be read alongside its prediction without a join. No
duplicate safety database is introduced.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c3f7a08e21b4'
down_revision: Union[str, Sequence[str], None] = 'bd2e1f4a9c31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('safety_flags', sa.Column('message_key', sa.String(length=50), nullable=True))
    op.add_column('safety_flags', sa.Column('first_detected_date', sa.Date(), nullable=True))
    op.add_column('safety_flags', sa.Column('last_observed_date', sa.Date(), nullable=True))
    op.add_column('safety_flags', sa.Column('triggering_statistics', sa.JSON(), nullable=True))
    op.add_column('safety_flags', sa.Column('detection_version', sa.String(length=30), nullable=True))

    op.add_column('circadian_labels', sa.Column('safe_output_status', sa.String(length=30), nullable=True))
    op.add_column('circadian_labels', sa.Column('recommendation_suppressed', sa.Boolean(), nullable=True))
    op.add_column('circadian_labels', sa.Column('safety_severity', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('circadian_labels', 'safety_severity')
    op.drop_column('circadian_labels', 'recommendation_suppressed')
    op.drop_column('circadian_labels', 'safe_output_status')

    op.drop_column('safety_flags', 'detection_version')
    op.drop_column('safety_flags', 'triggering_statistics')
    op.drop_column('safety_flags', 'last_observed_date')
    op.drop_column('safety_flags', 'first_detected_date')
    op.drop_column('safety_flags', 'message_key')

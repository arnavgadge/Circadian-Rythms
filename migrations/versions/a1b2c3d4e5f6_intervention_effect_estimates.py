"""intervention effect estimates (Phase 12)

Revision ID: a1b2c3d4e5f6
Revises: 6af552384ca4
Create Date: 2026-09-09 00:00:00.000000

Adds ``intervention_effect_estimates`` only -- purely additive, no
changes to any existing table. ``intervention_log`` (compliance_binary/
compliance_degree/actual_value_*/target_value_* etc.) already carried
everything Phase 12 needed for the day-by-day facts; this migration
only adds storage for the derived, versioned, recomputable effect
estimate itself (see docs/intervention_effectiveness.md
"Recomputation").
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '6af552384ca4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'intervention_effect_estimates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('participant_id', sa.Integer(), nullable=False),
        sa.Column('recommendation_id', sa.Integer(), nullable=False),
        sa.Column('measurement_phase', sa.Integer(), nullable=False),
        sa.Column('interpretation', sa.String(length=30), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=True),
        sa.Column('period_end', sa.Date(), nullable=True),
        sa.Column('effect_estimate', sa.Float(), nullable=True),
        sa.Column('confidence_interval_lower', sa.Float(), nullable=True),
        sa.Column('confidence_interval_upper', sa.Float(), nullable=True),
        sa.Column('standard_error', sa.Float(), nullable=True),
        sa.Column('r_squared', sa.Float(), nullable=True),
        sa.Column('n_observations', sa.Integer(), nullable=True),
        sa.Column('compliance_rate', sa.Float(), nullable=True),
        sa.Column('confound_flag', sa.Boolean(), nullable=False),
        sa.Column('methodology_version', sa.String(length=30), nullable=False),
        sa.Column('model_version', sa.String(length=50), nullable=True),
        sa.Column('diagnostics', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['participant_id'], ['participants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recommendation_id'], ['recommendations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_effect_estimates_participant_intervention',
        'intervention_effect_estimates',
        ['participant_id', 'recommendation_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_effect_estimates_participant_intervention', table_name='intervention_effect_estimates')
    op.drop_table('intervention_effect_estimates')

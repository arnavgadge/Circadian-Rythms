"""personal effect model metadata (Phase 13)

Revision ID: bd2e1f4a9c31
Revises: a1b2c3d4e5f6
Create Date: 2026-09-09 00:00:00.000000

Adds four nullable columns to the existing ``personal_effect_models``
table -- purely additive, no changes to any other table. ``bandit_state``
already carried everything Phase 13's contextual bandit needed
(posterior_mean/posterior_variance/total_pulls/total_reward/last_updated).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'bd2e1f4a9c31'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('personal_effect_models', sa.Column('confidence_interval_lower', sa.Float(), nullable=True))
    op.add_column('personal_effect_models', sa.Column('confidence_interval_upper', sa.Float(), nullable=True))
    op.add_column('personal_effect_models', sa.Column('model_version', sa.String(length=30), nullable=True))
    op.add_column('personal_effect_models', sa.Column('evidence_source', sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column('personal_effect_models', 'evidence_source')
    op.drop_column('personal_effect_models', 'model_version')
    op.drop_column('personal_effect_models', 'confidence_interval_upper')
    op.drop_column('personal_effect_models', 'confidence_interval_lower')

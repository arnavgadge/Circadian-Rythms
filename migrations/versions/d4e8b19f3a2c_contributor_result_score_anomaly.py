"""contributor_results score/anomaly columns (Phase 15)

Revision ID: d4e8b19f3a2c
Revises: c3f7a08e21b4
Create Date: 2026-09-09 00:00:00.000000

Purely additive: two nullable columns on ``contributor_results`` so the
Phase 15 API can expose ``contributor_score``/``today_anomaly`` without
recomputing them at read time -- Phase 9 already computes both, Phase
11's original persistence simply did not store them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd4e8b19f3a2c'
down_revision: Union[str, Sequence[str], None] = 'c3f7a08e21b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contributor_results', sa.Column('contributor_score', sa.Float(), nullable=True))
    op.add_column('contributor_results', sa.Column('today_anomaly', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('contributor_results', 'today_anomaly')
    op.drop_column('contributor_results', 'contributor_score')

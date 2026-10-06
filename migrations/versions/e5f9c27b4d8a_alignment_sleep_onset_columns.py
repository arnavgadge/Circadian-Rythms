"""alignment_results ideal/actual sleep onset columns (Phase 16)

Revision ID: e5f9c27b4d8a
Revises: d4e8b19f3a2c
Create Date: 2026-09-09 00:00:00.000000

Purely additive: two nullable Time columns on ``alignment_results`` so
the Phase 16 UI's clock visualization can show estimated DLMO vs.
ideal vs. actual sleep onset without the frontend computing anything --
Phase 8 already computes both values, Phase 11's original persistence
simply did not store them.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5f9c27b4d8a'
down_revision: Union[str, Sequence[str], None] = 'd4e8b19f3a2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('alignment_results', sa.Column('ideal_sleep_onset_time', sa.Time(), nullable=True))
    op.add_column('alignment_results', sa.Column('actual_sleep_onset_time', sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column('alignment_results', 'actual_sleep_onset_time')
    op.drop_column('alignment_results', 'ideal_sleep_onset_time')

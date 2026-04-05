"""add device_id to terminal_configs

Revision ID: f1e2d3c4b5a6
Revises: c20d1a5dfbe0
Create Date: 2026-04-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f1e2d3c4b5a6'
down_revision: Union[str, None] = 'c20d1a5dfbe0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('terminal_configs', sa.Column('device_id', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('terminal_configs', 'device_id')

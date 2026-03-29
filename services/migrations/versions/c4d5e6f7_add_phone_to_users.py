"""add phone to users

Revision ID: c4d5e6f7
Revises: b3c4d5e6
Create Date: 2026-03-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c4d5e6f7'
down_revision: Union[str, None] = 'b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('phone', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'phone')

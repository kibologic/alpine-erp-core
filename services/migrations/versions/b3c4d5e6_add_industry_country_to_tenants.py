"""add industry and country to tenants

Revision ID: b3c4d5e6
Revises: 1c92a86375e9
Create Date: 2026-03-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b3c4d5e6'
down_revision: Union[str, None] = '1c92a86375e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tenants', sa.Column('industry', sa.String(100), nullable=True))
    op.add_column('tenants', sa.Column('country', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('tenants', 'country')
    op.drop_column('tenants', 'industry')

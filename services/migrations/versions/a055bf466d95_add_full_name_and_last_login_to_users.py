"""add full_name and last_login to users

Revision ID: a055bf466d95
Revises: 5e8a9d2b
Create Date: 2026-03-28 23:39:06.015343

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a055bf466d95'
down_revision: Union[str, None] = '5e8a9d2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('full_name', sa.String(), nullable=True))
    op.add_column('users', sa.Column('last_login', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'last_login')
    op.drop_column('users', 'full_name')

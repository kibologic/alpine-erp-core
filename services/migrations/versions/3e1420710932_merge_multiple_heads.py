"""Merge multiple heads

Revision ID: 3e1420710932
Revises: b761eff81c1d, f1e2d3c4b5a6
Create Date: 2026-04-05 14:17:21.612899

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e1420710932'
down_revision: Union[str, None] = ('b761eff81c1d', 'f1e2d3c4b5a6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

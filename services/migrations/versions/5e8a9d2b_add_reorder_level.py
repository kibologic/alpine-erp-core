"""add reorder_level to products

Revision ID: 5e8a9d2b
Revises: 20260325
Create Date: 2026-03-28 11:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5e8a9d2b"
down_revision: Union[str, None] = "20260325"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column("products", sa.Column("reorder_level", sa.Numeric(12, 2), nullable=False, server_default="10.0"))

def downgrade() -> None:
    op.drop_column("products", "reorder_level")

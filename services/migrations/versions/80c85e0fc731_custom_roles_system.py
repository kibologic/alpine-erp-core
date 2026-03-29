"""custom_roles_system

Revision ID: 80c85e0fc731
Revises: c4d5e6f7
Create Date: 2026-03-29 06:50:04.425506

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '80c85e0fc731'
down_revision: Union[str, None] = 'c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'custom_roles',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('tenant_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('is_system', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_by', sa.UUID(as_uuid=False), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table(
        'role_atoms',
        sa.Column('id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('role_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('atom', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['custom_roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.add_column('users', sa.Column('custom_role_id', sa.UUID(as_uuid=False), nullable=True))
    op.create_foreign_key(
        'fk_users_custom_role_id',
        'users', 'custom_roles',
        ['custom_role_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_users_custom_role_id', 'users', type_='foreignkey')
    op.drop_column('users', 'custom_role_id')
    op.drop_table('role_atoms')
    op.drop_table('custom_roles')

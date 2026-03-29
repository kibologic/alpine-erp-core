"""account_status org_invites drop_role_field join_request_role

Revision ID: c9edeb34f5a9
Revises: 80c85e0fc731
Create Date: 2026-03-29 12:32:52.401755

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9edeb34f5a9'
down_revision: Union[str, None] = '80c85e0fc731'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # users.account_status
    op.add_column('users', sa.Column('account_status', sa.String(length=50), server_default='pending', nullable=True))
    op.drop_column('users', 'role')

    # join_requests.role_id
    op.add_column('join_requests', sa.Column('role_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_join_requests_role_id', 'join_requests', 'custom_roles', ['role_id'], ['id'], ondelete='SET NULL')

    # org_invites
    op.create_table(
        'org_invites',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('invited_by', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('role_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(length=50), server_default='pending', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['custom_roles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('org_invites')
    op.drop_constraint('fk_join_requests_role_id', 'join_requests', type_='foreignkey')
    op.drop_column('join_requests', 'role_id')
    op.add_column('users', sa.Column('role', sa.VARCHAR(length=50), server_default='staff', autoincrement=False, nullable=True))
    op.drop_column('users', 'account_status')

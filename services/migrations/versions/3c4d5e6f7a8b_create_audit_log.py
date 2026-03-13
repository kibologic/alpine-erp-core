"""create immutable audit log

Revision ID: 3c4d5e6f7a8b
Revises: 2b3c4d5e_procurement
Create Date: 2026-03-06
"""
from alembic import op

revision = "3c4d5e6f7a8b"
down_revision = "2b3c4d5e_procurement"
branch_labels = None
depends_on = None
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY


def upgrade() -> None:
    op.create_table(
        "constitutional_audit_log",
        sa.Column(
            "entry_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("previous_entry_hash", sa.String(64), nullable=False),
        sa.Column("entry_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("event_name", sa.String(128), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_context_id", UUID(as_uuid=True), nullable=False),
        sa.Column("causal_depth", sa.Integer(), nullable=False, default=0),
        sa.Column(
            "cumulative_risk_score", sa.Integer(), nullable=False, default=0
        ),
        sa.Column("actor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("device_hash", sa.String(64), nullable=False),
        sa.Column(
            "capability_snapshot_hash", sa.String(64), nullable=False
        ),
        sa.Column(
            "delegation_chain",
            ARRAY(UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("block_reason", sa.String(64), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("approval_capability", sa.String(128), nullable=True),
        sa.Column(
            "guardrail_step_reached", sa.Integer(), nullable=False
        ),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "evaluated_at", sa.TIMESTAMP(timezone=True), nullable=False
        ),
        sa.Column(
            "logged_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "jurisdiction_scope",
            ARRAY(sa.String(8)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("payload_hash", sa.String(64), nullable=False),
    )

    op.create_index(
        "idx_constitutional_audit_log_org_logged",
        "constitutional_audit_log",
        ["org_id", sa.text("logged_at DESC")],
    )
    op.create_index(
        "idx_constitutional_audit_log_workflow",
        "constitutional_audit_log",
        ["workflow_context_id", sa.text("causal_depth ASC")],
    )
    op.create_index(
        "idx_constitutional_audit_log_outcome",
        "constitutional_audit_log",
        ["org_id", "outcome", sa.text("logged_at DESC")],
    )
    op.create_index(
        "idx_constitutional_audit_log_hash", "constitutional_audit_log", ["entry_hash"]
    )

    op.execute("""
        CREATE RULE no_update_constitutional_audit_log AS
            ON UPDATE TO constitutional_audit_log DO INSTEAD NOTHING
    """)
    op.execute("""
        CREATE RULE no_delete_constitutional_audit_log AS
            ON DELETE TO constitutional_audit_log DO INSTEAD NOTHING
    """)


def downgrade() -> None:
    op.drop_table("constitutional_audit_log")

"""Add procurement domain models and extend Product for TSI readiness

Revision ID: 2b3c4d5e_procurement
Revises: 1a2b3c4d
Create Date: 2026-03-05

Tables added:
    suppliers
    purchase_orders
    purchase_order_lines
    supplier_performance_logs

Product columns added (nullable, no breaking change):
    metadata (JSONB)
    canonical_material_id (VARCHAR 255)
    quality_tier (ENUM product_quality_tier)

Enums added:
    purchase_order_status
    supplier_metric_type
    product_quality_tier

All tables are scoped by tenant_id with RESTRICT cascade rules.
Indexes added on tenant_id, supplier_id, purchase_order_id.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = "2b3c4d5e_procurement"
down_revision = "1a2b3c4d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Suppliers ──────────────────────────────────────────────────────────────
    op.create_table(
        "suppliers",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False),
                  sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="TRUE"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_supplier_tenant_name"),
    )
    op.create_index("ix_supplier_tenant_id", "suppliers", ["tenant_id"])

    # ── Purchase Orders ────────────────────────────────────────────────────────
    op.create_table(
        "purchase_orders",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False),
                  sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_id", UUID(as_uuid=False),
                  sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("po_number", sa.String(80), nullable=False),
        sa.Column("status", sa.Enum("DRAFT","APPROVED","SENT","PARTIALLY_RECEIVED",
                                    "RECEIVED","CLOSED","CANCELLED",
                                    name="purchase_order_status"),
                  nullable=False, server_default="DRAFT"),
        sa.Column("total_amount", sa.Numeric(16, 2), nullable=True),
        sa.Column("currency", sa.String(10), nullable=False, server_default="MWK"),
        sa.Column("expected_delivery_date", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "po_number", name="uq_po_tenant_number"),
    )
    op.create_index("ix_po_tenant_id", "purchase_orders", ["tenant_id"])
    op.create_index("ix_po_supplier_id", "purchase_orders", ["supplier_id"])

    # ── Purchase Order Lines ───────────────────────────────────────────────────
    op.create_table(
        "purchase_order_lines",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False),
                  sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purchase_order_id", UUID(as_uuid=False),
                  sa.ForeignKey("purchase_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=False),
                  sa.ForeignKey("products.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity_ordered", sa.Numeric(12, 3), nullable=False),
        sa.Column("quantity_received", sa.Numeric(12, 3), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(12, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("line_metadata", JSONB, nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "purchase_order_id", "product_id",
            name="uq_pol_tenant_po_product"
        ),
    )
    op.create_index("ix_pol_tenant_id", "purchase_order_lines", ["tenant_id"])
    op.create_index("ix_pol_po_id", "purchase_order_lines", ["purchase_order_id"])

    # ── Supplier Performance Logs ──────────────────────────────────────────────
    op.create_table(
        "supplier_performance_logs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False),
                  sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("supplier_id", UUID(as_uuid=False),
                  sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("purchase_order_id", UUID(as_uuid=False),
                  sa.ForeignKey("purchase_orders.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("metric_type", sa.Enum("DELIVERY_LATENCY","DEFECT_RATE",
                                         "FULFILLMENT_RATE","INVOICE_ACCURACY",
                                         name="supplier_metric_type"), nullable=False),
        sa.Column("metric_value", sa.Numeric(14, 4), nullable=True),
        sa.Column("metric_payload", JSONB, nullable=True),
        sa.Column("recorded_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_spl_tenant_id", "supplier_performance_logs", ["tenant_id"])
    op.create_index("ix_spl_supplier_id", "supplier_performance_logs", ["supplier_id"])
    op.create_index("ix_spl_po_id", "supplier_performance_logs", ["purchase_order_id"])

    # ── Extend Product (nullable — no breaking change) ─────────────────────────
    # op.add_column does not fire _on_table_create, so create the enum type
    # explicitly via raw SQL (idempotent DO block).
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE product_quality_tier AS ENUM (
                'ECONOMY', 'STANDARD', 'PREMIUM', 'CERTIFIED'
            );
        EXCEPTION WHEN duplicate_object THEN null;
        END $$;
    """)
    op.add_column("products", sa.Column("extra_data", JSONB, nullable=True))
    op.add_column("products", sa.Column("canonical_material_id", sa.String(255), nullable=True))
    op.add_column("products", sa.Column(
        "quality_tier",
        sa.Enum("ECONOMY","STANDARD","PREMIUM","CERTIFIED", name="product_quality_tier", create_type=False),
        nullable=True
    ))


def downgrade() -> None:
    # Reverse Product extensions
    op.drop_column("products", "quality_tier")
    op.drop_column("products", "canonical_material_id")
    op.drop_column("products", "extra_data")

    # Drop procurement tables (reverse FK order)
    op.drop_table("supplier_performance_logs")
    op.drop_table("purchase_order_lines")
    op.drop_table("purchase_orders")
    op.drop_table("suppliers")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS product_quality_tier")
    op.execute("DROP TYPE IF EXISTS supplier_metric_type")
    op.execute("DROP TYPE IF EXISTS purchase_order_status")

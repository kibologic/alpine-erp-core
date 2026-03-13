"""add_pos_and_inventory

Revision ID: 1a2b3c4d
Revises: 69a0986c
Create Date: 2026-03-03 08:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1a2b3c4d"
down_revision: Union[str, None] = "69a0986c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # Categories
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_categories_tenant_id", "categories", ["tenant_id"])

    # Products
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("sku", sa.String(100), nullable=False),
        sa.Column("barcode", sa.String(100), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=False, server_default="0.0"),
        sa.Column("cost", sa.Numeric(12, 2), nullable=False, server_default="0.0"),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="0.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_products_tenant_id", "products", ["tenant_id"])
    op.create_index("ix_products_sku", "products", ["sku"])

    # Stock Movements
    op.create_table(
        "stock_movements",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("reason", sa.String(100), nullable=False),
        sa.Column("reference_type", sa.String(50), nullable=True),
        sa.Column("reference_id", sa.String(100), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_stock_movements_tenant_id", "stock_movements", ["tenant_id"])
    op.create_index("ix_stock_movements_product_id", "stock_movements", ["product_id"])

    # Customers
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"])

    # Cash Sessions
    op.create_table(
        "cash_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("register_id", sa.String(100), nullable=False),
        sa.Column("opened_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("opening_float", sa.Numeric(12, 2), nullable=False, server_default="0.0"),
        sa.Column("closed_by", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("closing_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("discrepancy", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("opened_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_cash_sessions_tenant_id", "cash_sessions", ["tenant_id"])

    # Sales
    op.create_table(
        "sales",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sale_number", sa.String(50), nullable=False, unique=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cashier_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("cash_sessions.id"), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0.0"),
        sa.Column("tax", sa.Numeric(12, 2), nullable=False, server_default="0.0"),
        sa.Column("discount", sa.Numeric(12, 2), nullable=False, server_default="0.0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0.0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sales_tenant_id", "sales", ["tenant_id"])
    op.create_index("ix_sales_sale_number", "sales", ["sale_number"])

    # Sale Lines
    op.create_table(
        "sale_lines",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("sale_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount", sa.Numeric(12, 2), nullable=False, server_default="0.0"),
        sa.Column("tax", sa.Numeric(12, 2), nullable=False, server_default="0.0"),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
    )
    op.create_index("ix_sale_lines_sale_id", "sale_lines", ["sale_id"])

    # Payments
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("sale_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("sales.id", ondelete="CASCADE"), nullable=False),
        sa.Column("method", sa.String(50), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_payments_sale_id", "payments", ["sale_id"])

    # Stock on Hand View
    op.execute("""
        CREATE VIEW stock_on_hand AS
        SELECT
            tenant_id,
            product_id,
            SUM(quantity) as quantity
        FROM
            stock_movements
        GROUP BY
            tenant_id, product_id;
    """)

def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS stock_on_hand")
    op.drop_table("payments")
    op.drop_table("sale_lines")
    op.drop_table("sales")
    op.drop_table("cash_sessions")
    op.drop_table("customers")
    op.drop_table("stock_movements")
    op.drop_table("products")
    op.drop_table("categories")

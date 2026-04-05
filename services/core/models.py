import enum
import uuid
from datetime import datetime, date
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, String, Text, Numeric, Integer, JSON, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


# ─── Enums ────────────────────────────────────────────────────────────────────

class PurchaseOrderStatus(str, enum.Enum):
    DRAFT             = "DRAFT"
    APPROVED          = "APPROVED"
    SENT              = "SENT"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    RECEIVED          = "RECEIVED"
    CLOSED            = "CLOSED"
    CANCELLED         = "CANCELLED"


class SupplierMetricType(str, enum.Enum):
    DELIVERY_LATENCY  = "DELIVERY_LATENCY"
    DEFECT_RATE       = "DEFECT_RATE"
    FULFILLMENT_RATE  = "FULFILLMENT_RATE"
    INVOICE_ACCURACY  = "INVOICE_ACCURACY"
    # Extend without migration — append only


class ProductQualityTier(str, enum.Enum):
    ECONOMY   = "ECONOMY"
    STANDARD  = "STANDARD"
    PREMIUM   = "PREMIUM"
    CERTIFIED = "CERTIFIED"


class AccountStatus(str, enum.Enum):
    pending = "pending"
    active = "active"
    suspended = "suspended"


def now_utc() -> datetime:
    return datetime.utcnow()


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    license_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tier: Mapped[str] = mapped_column(String(50), nullable=False, default="free")
    terminal_device_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    fiscal_provider: Mapped[Optional[str]] = mapped_column(
        String, nullable=True, default="noop"
    )
    fiscal_config: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=dict
    )
    default_locale: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="en-US")
    default_currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, default="MWK")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    users: Mapped[list["User"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(), nullable=True)
    account_status: Mapped[str] = mapped_column(String(50), default="pending", server_default="pending")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    custom_role_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("custom_roles.id", ondelete="SET NULL"), nullable=True
    )

    tenant: Mapped["Tenant"] = relationship(back_populates="users")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")
    user_tenants: Mapped[list["UserTenant"]] = relationship(back_populates="user")
    auth_tokens: Mapped[list["AuthToken"]] = relationship(back_populates="user")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    tenant: Mapped["Tenant"] = relationship(back_populates="audit_logs")
    user: Mapped["User | None"] = relationship(back_populates="audit_logs")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    tenant: Mapped["Tenant"] = relationship()
    products: Mapped[list["Product"]] = relationship(back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    category_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(100), nullable=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    reorder_level: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=10.0)
    tax_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    # Phase 2 — TSI-ready extensions (all nullable, backward compatible)
    extra_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    canonical_material_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quality_tier: Mapped[str | None] = mapped_column(
        Enum(ProductQualityTier, name="product_quality_tier", create_type=False), nullable=True
    )
    # ── Fiscal Compliance Layer ────────────────────────
    unspsc_code: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    fiscal_codes: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True, default=dict
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_product_tenant_sku"),
    )

    tenant: Mapped["Tenant"] = relationship()
    category: Mapped["Category | None"] = relationship(back_populates="products")
    stock_movements: Mapped[list["StockMovement"]] = relationship(back_populates="product")


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    reference_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    tenant: Mapped["Tenant"] = relationship()
    product: Mapped["Product"] = relationship(back_populates="stock_movements")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    tenant: Mapped["Tenant"] = relationship()


class CashSession(Base):
    __tablename__ = "cash_sessions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    register_id: Mapped[str] = mapped_column(String(100), nullable=False)
    opened_by: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=False,
    )
    opening_float: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    closed_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=True,
    )
    closing_amount: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    discrepancy: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tenant: Mapped["Tenant"] = relationship()


class Sale(Base):
    __tablename__ = "sales"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    sale_number: Mapped[str] = mapped_column(String(50), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
    )
    cashier_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=False,
    )
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("cash_sessions.id"),
        nullable=False,
    )
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    tax: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    discount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    __table_args__ = (
        UniqueConstraint("tenant_id", "sale_number", name="uq_sale_tenant_number"),
    )

    tenant: Mapped["Tenant"] = relationship()
    lines: Mapped[list["SaleLine"]] = relationship(back_populates="sale", cascade="all, delete-orphan")
    payments: Mapped[list["Payment"]] = relationship(back_populates="sale", cascade="all, delete-orphan")


class SaleLine(Base):
    __tablename__ = "sale_lines"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    sale_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("sales.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("products.id"),
        nullable=False,
    )
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    discount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    tax: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    tenant: Mapped["Tenant"] = relationship()
    sale: Mapped["Sale"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship()


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    sale_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("sales.id", ondelete="CASCADE"),
        nullable=False,
    )
    method: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    tenant: Mapped["Tenant"] = relationship()
    sale: Mapped["Sale"] = relationship(back_populates="payments")


# ─── Procurement Domain Models ────────────────────────────────────────────────

class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_supplier_tenant_name"),
        Index("ix_supplier_tenant_id", "tenant_id"),
    )

    tenant: Mapped["Tenant"] = relationship()
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(back_populates="supplier")
    performance_logs: Mapped[list["SupplierPerformanceLog"]] = relationship(back_populates="supplier")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    supplier_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    po_number: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(PurchaseOrderStatus, name="purchase_order_status", create_type=False),
        nullable=False,
        default=PurchaseOrderStatus.DRAFT,
    )
    total_amount: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="MWK")
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)

    __table_args__ = (
        UniqueConstraint("tenant_id", "po_number", name="uq_po_tenant_number"),
        Index("ix_po_tenant_id", "tenant_id"),
        Index("ix_po_supplier_id", "supplier_id"),
    )

    tenant: Mapped["Tenant"] = relationship()
    supplier: Mapped["Supplier"] = relationship(back_populates="purchase_orders")
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        back_populates="purchase_order", cascade="all, delete-orphan"
    )
    performance_logs: Mapped[list["SupplierPerformanceLog"]] = relationship(
        back_populates="purchase_order"
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    purchase_order_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity_ordered: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    quantity_received: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=0.0)
    unit_cost: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0.0)
    # IMPORTANT: JSONB metadata — forward-compatible AI/TSI annotation slot
    line_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "purchase_order_id", "product_id",
            name="uq_pol_tenant_po_product"
        ),
        Index("ix_pol_tenant_id", "tenant_id"),
        Index("ix_pol_po_id", "purchase_order_id"),
    )

    tenant: Mapped["Tenant"] = relationship()
    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship()


class SupplierPerformanceLog(Base):
    """
    Raw structured performance data scaffold.
    No intelligence computed here — data capture only.
    TSI layer will read and derive scores from this table.
    """
    __tablename__ = "supplier_performance_logs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )
    supplier_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("suppliers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    purchase_order_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    metric_type: Mapped[str] = mapped_column(
        Enum(SupplierMetricType, name="supplier_metric_type", create_type=False), nullable=False
    )
    # Numeric value (e.g. latency_days=3) or complex payload (e.g. {"defects": 2, "batch_size": 100})
    metric_value: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    metric_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    __table_args__ = (
        Index("ix_spl_tenant_id", "tenant_id"),
        Index("ix_spl_supplier_id", "supplier_id"),
        Index("ix_spl_po_id", "purchase_order_id"),
    )

    tenant: Mapped["Tenant"] = relationship()
    supplier: Mapped["Supplier"] = relationship(back_populates="performance_logs")
    purchase_order: Mapped["PurchaseOrder"] = relationship(back_populates="performance_logs")


class UserTenant(Base):
    __tablename__ = "user_tenants"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="cashier")
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_user_tenants"),
    )

    user: Mapped["User"] = relationship(back_populates="user_tenants")
    tenant: Mapped["Tenant"] = relationship()


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

    user: Mapped["User"] = relationship(back_populates="auth_tokens")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    token: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped[Optional["Tenant"]] = relationship()


class JoinRequest(Base):
    __tablename__ = "join_requests"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id"), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, default="pending")
    role_id: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), ForeignKey("custom_roles.id", ondelete="SET NULL"), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)


class OrgInvite(Base):
    __tablename__ = "org_invites"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    invited_by: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    role_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("custom_roles.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CustomRole(Base):
    __tablename__ = "custom_roles"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[Optional[str]] = mapped_column(UUID(as_uuid=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped["Tenant"] = relationship()
    atoms: Mapped[list["RoleAtom"]] = relationship(back_populates="role", cascade="all, delete-orphan")


class RoleAtom(Base):
    __tablename__ = "role_atoms"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("custom_roles.id", ondelete="CASCADE"), nullable=False
    )
    atom: Mapped[str] = mapped_column(String, nullable=False)

    tenant: Mapped["Tenant"] = relationship()
    role: Mapped["CustomRole"] = relationship(back_populates="atoms")


class FiscalSubmission(Base):
    __tablename__ = "fiscal_submissions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False
    )
    sale_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("sales.id", ondelete="CASCADE"),
        nullable=False
    )
    provider: Mapped[str] = mapped_column(
        String, default="noop"
    )
    fiscal_code: Mapped[Optional[str]] = mapped_column(
        String, nullable=True
    )
    qr_code: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    receipt_block: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    status: Mapped[str] = mapped_column(
        String, default="pending"
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    offline: Mapped[bool] = mapped_column(
        Boolean, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tenant: Mapped["Tenant"] = relationship()
    sale: Mapped["Sale"] = relationship()


# ─── POS Selling Mode Engine ──────────────────────────────────────────────────

class TerminalConfig(Base):
    __tablename__ = "terminal_configs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    terminal_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="Main Terminal")
    device_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    enabled_modes: Mapped[list] = mapped_column(JSONB, default=lambda: ["instant"])
    default_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="instant")
    config: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "terminal_id", name="uq_terminal_config_tenant_terminal"),
    )

    tenant: Mapped["Tenant"] = relationship()


class Tab(Base):
    __tablename__ = "tabs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("cash_sessions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    tax: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    created_by: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["Tenant"] = relationship()
    lines: Mapped[list["TabLine"]] = relationship(back_populates="tab", cascade="all, delete-orphan")


class TabLine(Base):
    __tablename__ = "tab_lines"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    tab_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tabs.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=1.0)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    tax: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0.0)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped["Tenant"] = relationship()
    tab: Mapped["Tab"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship()


class KitchenOrder(Base):
    __tablename__ = "kitchen_orders"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("cash_sessions.id", ondelete="CASCADE"), nullable=False
    )
    tab_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("tabs.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped["Tenant"] = relationship()
    tab: Mapped[Optional["Tab"]] = relationship()
    lines: Mapped[list["KitchenOrderLine"]] = relationship(back_populates="kitchen_order", cascade="all, delete-orphan")


class KitchenOrderLine(Base):
    __tablename__ = "kitchen_order_lines"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    kitchen_order_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("kitchen_orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=1.0)
    notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    tenant: Mapped["Tenant"] = relationship()
    kitchen_order: Mapped["KitchenOrder"] = relationship(back_populates="lines")
    product: Mapped["Product"] = relationship()


class Media(Base):
    __tablename__ = "media"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploaded_by: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    entity: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tenant: Mapped["Tenant"] = relationship()

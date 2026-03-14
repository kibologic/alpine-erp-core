from decimal import Decimal
from typing import Optional, Sequence
from uuid import uuid4

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from core.models import Product, Category, StockMovement
from core.audit import log_event
from . import schemas


async def get_categories(session: AsyncSession, tenant_id: str) -> Sequence[Category]:
    result = await session.execute(
        select(Category).where(Category.tenant_id == tenant_id).order_by(Category.name)
    )
    return result.scalars().all()


async def create_category(
    session: AsyncSession, tenant_id: str, data: schemas.CategoryCreate
) -> Category:
    category = Category(
        tenant_id=tenant_id,
        name=data.name,
    )
    session.add(category)
    await session.commit()
    await session.refresh(category)
    
    # Audit log
    await log_event(session, tenant_id, "SYSTEM", "CREATE", "Category", str(category.id), {"name": category.name})
    
    return category


async def get_products(
    session: AsyncSession, tenant_id: str, category_id: Optional[str] = None
) -> Sequence[dict]:
    # We join with the SQL view to get the current quantity.
    # UUID columns are cast to text so asyncpg returns strings, not UUID objects.
    query = text("""
        SELECT
            p.id::text,
            p.tenant_id::text,
            p.category_id::text,
            p.name,
            p.sku,
            p.barcode,
            p.price,
            p.cost,
            p.tax_rate,
            p.is_active,
            p.created_at,
            p.extra_data,
            p.canonical_material_id,
            p.quality_tier,
            COALESCE(s.quantity, 0) AS stock_quantity
        FROM products p
        LEFT JOIN stock_on_hand s ON p.id = s.product_id AND p.tenant_id = s.tenant_id
        WHERE p.tenant_id = :t
    """)
    params = {"t": tenant_id}
    if category_id:
        query = text(str(query) + " AND p.category_id = :c")
        params["c"] = category_id
    
    result = await session.execute(query, params)
    return result.mappings().all()


async def create_product(
    session: AsyncSession, tenant_id: str, data: schemas.ProductCreate
) -> Product:
    product = Product(
        tenant_id=tenant_id,
        category_id=data.category_id,
        name=data.name,
        sku=data.sku,
        barcode=data.barcode,
        price=data.price,
        cost=data.cost,
        tax_rate=data.tax_rate,
        is_active=data.is_active,
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    
    # Audit log
    await log_event(session, tenant_id, "SYSTEM", "CREATE", "Product", str(product.id), {"sku": product.sku, "name": product.name})
    
    return product


async def adjust_stock(
    session: AsyncSession, 
    tenant_id: str, 
    data: schemas.StockAdjustmentCreate,
    user_id: Optional[str] = None
) -> StockMovement:
    movement = StockMovement(
        tenant_id=tenant_id,
        product_id=data.product_id,
        quantity=data.quantity,
        reason=data.reason,
        created_by=user_id,
        reference_type="Manual Adjustment"
    )
    session.add(movement)
    await session.commit()
    await session.refresh(movement)
    
    # Audit log
    await log_event(session, tenant_id, user_id or "SYSTEM", "ADJUST_STOCK", "Product", data.product_id, {"qty": str(data.quantity), "reason": data.reason})
    
    return movement


async def get_stock_on_hand(session: AsyncSession, tenant_id: str, product_id: str) -> Decimal:
    # Query the SQL View created in the migration
    result = await session.execute(
        text("SELECT quantity FROM stock_on_hand WHERE tenant_id = :t AND product_id = :p"),
        {"t": tenant_id, "p": product_id}
    )
    row = result.fetchone()
    return Decimal(str(row[0])) if row else Decimal("0")


async def get_inventory_valuation(session: AsyncSession, tenant_id: str) -> schemas.InventoryValuationResponse:
    # Sum(Product.cost * StockOnHand.quantity)
    # Using the view joined with products table
    query = text("""
        SELECT 
            COUNT(p.id) as total_items,
            SUM(p.cost * COALESCE(s.quantity, 0)) as total_value
        FROM 
            products p
        LEFT JOIN 
            stock_on_hand s ON p.id = s.product_id AND p.tenant_id = s.tenant_id
        WHERE 
            p.tenant_id = :t AND p.is_active = true
    """)
    
    result = await session.execute(query, {"t": tenant_id})
    row = result.fetchone()
    
    return schemas.InventoryValuationResponse(
        total_items=row[0] if row and row[0] else 0,
        total_value=Decimal(str(row[1])) if row and row[1] else Decimal("0")
    )


from core.models import Customer

async def get_customers(session: AsyncSession, tenant_id: str) -> Sequence[Customer]:
    result = await session.execute(
        select(Customer).where(Customer.tenant_id == tenant_id).order_by(Customer.created_at.desc())
    )
    return result.scalars().all()


async def create_customer(
    session: AsyncSession, tenant_id: str, data: schemas.CustomerCreate
) -> Customer:
    customer = Customer(
        tenant_id=tenant_id,
        name=data.name,
        phone=data.phone,
        email=data.email,
    )
    session.add(customer)
    await session.commit()
    await session.refresh(customer)
    
    # Audit log
    await log_event(session, tenant_id, "SYSTEM", "CREATE", "Customer", str(customer.id), {"name": customer.name})
    
    return customer

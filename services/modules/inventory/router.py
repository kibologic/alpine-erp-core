from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.auth import get_current_tenant
from core.limits import LimitEnforcer, get_limit_enforcer
from core.models import StockMovement, Supplier
from . import schemas, service

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("/categories", response_model=List[schemas.CategoryResponse])
async def list_categories(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    return await service.get_categories(session, tenant_id)


@router.post("/categories", response_model=schemas.CategoryResponse)
async def create_category(
    data: schemas.CategoryCreate,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    return await service.create_category(session, tenant_id, data)


@router.get("/products", response_model=List[schemas.ProductResponse])
async def list_products(
    category_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    return await service.get_products(session, tenant_id, category_id)


@router.post("/products", response_model=schemas.ProductResponse)
async def create_product(
    data: schemas.ProductCreate,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
    limits: LimitEnforcer = Depends(get_limit_enforcer),
):
    await limits.check_product_limit()
    return await service.create_product(session, tenant_id, data)


@router.post("/adjust", response_model=schemas.StockMovementResponse)
async def adjust_stock(
    data: schemas.StockAdjustmentCreate,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    # In a real app, we'd get the user_id from the auth token
    return await service.adjust_stock(session, tenant_id, data)


@router.get("/stock/{product_id}")
async def get_stock(
    product_id: str,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    qty = await service.get_stock_on_hand(session, tenant_id, product_id)
    return {"product_id": product_id, "quantity": qty}


@router.get("/valuation", response_model=schemas.InventoryValuationResponse)
async def get_valuation(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    return await service.get_inventory_valuation(session, tenant_id)


@router.get("/customers", response_model=List[schemas.CustomerResponse])
async def list_customers(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    return await service.get_customers(session, tenant_id)


@router.get("/movements")
async def list_movements(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    result = await session.execute(
        select(StockMovement)
        .where(StockMovement.tenant_id == tenant_id)
        .order_by(StockMovement.created_at.desc())
        .limit(100)
    )
    movements = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "product_id": str(m.product_id),
            "quantity": float(m.quantity),
            "reason": m.reason,
            "reference_type": m.reference_type,
            "reference_id": m.reference_id,
            "created_at": m.created_at.isoformat(),
        }
        for m in movements
    ]


@router.get("/stock-levels")
async def list_stock_levels(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    result = await session.execute(
        text("""
            SELECT p.id, p.name, p.sku, p.price,
                   c.name as category,
                   COALESCE(s.quantity, 0) as stock_quantity
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            LEFT JOIN stock_on_hand s ON p.id::text = s.product_id::text
                AND s.tenant_id::text = :tenant_id
            WHERE p.tenant_id::text = :tenant_id AND p.is_active = true
            ORDER BY p.name
        """),
        {"tenant_id": tenant_id}
    )
    rows = result.fetchall()
    return [
        {
            "id": str(r.id),
            "name": r.name,
            "sku": r.sku,
            "category": r.category,
            "price": float(r.price),
            "stock_quantity": float(r.stock_quantity),
            "status": "out_of_stock" if r.stock_quantity <= 0 else "low" if r.stock_quantity < 10 else "healthy",
        }
        for r in rows
    ]


@router.get("/suppliers")
async def list_suppliers(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    result = await session.execute(
        select(Supplier)
        .where(Supplier.tenant_id == tenant_id, Supplier.is_active == True)
        .order_by(Supplier.name)
    )
    suppliers = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "email": s.email,
            "phone": s.phone,
            "address": s.address,
            "created_at": s.created_at.isoformat(),
        }
        for s in suppliers
    ]


@router.post("/customers", response_model=schemas.CustomerResponse)
async def create_customer(
    data: schemas.CustomerCreate,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
    limits: LimitEnforcer = Depends(get_limit_enforcer),
):
    await limits.check_customer_limit()
    return await service.create_customer(session, tenant_id, data)

import io
from datetime import date
from typing import List, Optional

import openpyxl
from openpyxl.styles import Font
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.auth import get_current_tenant, verify_internal_token
from core.limits import LimitEnforcer, get_limit_enforcer
from core.models import Product, StockMovement, Supplier
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


@router.patch("/categories/{category_id}", response_model=schemas.CategoryResponse,
              dependencies=[Depends(verify_internal_token)])
async def update_category(
    category_id: str,
    data: schemas.CategoryUpdate,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    from core.models import Category
    result = await session.execute(
        select(Category).where(Category.id == category_id, Category.tenant_id == tenant_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    if data.name is not None:
        category.name = data.name
    await session.commit()
    await session.refresh(category)
    return category


@router.delete("/categories/{category_id}", status_code=204,
               dependencies=[Depends(verify_internal_token)])
async def delete_category(
    category_id: str,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    from core.models import Category
    result = await session.execute(
        select(Category).where(Category.id == category_id, Category.tenant_id == tenant_id)
    )
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    await session.delete(category)
    await session.commit()
    return Response(status_code=204)


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


@router.get("/stock-take/export", dependencies=[Depends(verify_internal_token)])
async def export_stock_take(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    result = await session.execute(
        text("""
            SELECT p.sku, p.name, COALESCE(s.quantity, 0) as stock_on_hand
            FROM products p
            LEFT JOIN stock_on_hand s ON p.id::text = s.product_id::text
                AND s.tenant_id::text = :tenant_id
            WHERE p.tenant_id::text = :tenant_id AND p.is_active = true
            ORDER BY p.name
        """),
        {"tenant_id": tenant_id},
    )
    rows = result.fetchall()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Stock Take"

    headers = ["SKU", "Product Name", "Stock On Hand", "Counted Quantity", "Variance", "Notes"]
    ws.append(headers)
    bold = Font(bold=True)
    for cell in ws[1]:
        cell.font = bold

    for row in rows:
        ws.append([row.sku, row.name, float(row.stock_on_hand), None, None, None])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"stock-take-{date.today().isoformat()}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/stock-take/import", dependencies=[Depends(verify_internal_token)])
async def import_stock_take(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    contents = await file.read()
    wb = openpyxl.load_workbook(io.BytesIO(contents), data_only=True)

    if "Stock Take" not in wb.sheetnames:
        raise HTTPException(status_code=400, detail="Sheet 'Stock Take' not found")

    ws = wb["Stock Take"]
    rows = list(ws.iter_rows(min_row=2, values_only=True))

    # Pre-load all products for this tenant keyed by SKU
    result = await session.execute(
        select(Product).where(Product.tenant_id == tenant_id, Product.is_active == True)
    )
    products_by_sku = {p.sku: p for p in result.scalars().all()}

    processed = 0
    adjusted = 0
    skipped = []
    movement_ids = []

    for row in rows:
        if not any(row):
            continue

        sku, _name, stock_on_hand, counted_qty, _variance, notes = (
            row[0], row[1], row[2], row[3], row[4], row[5]
        )

        if counted_qty is None or counted_qty == "":
            continue

        processed += 1

        if sku not in products_by_sku:
            skipped.append(str(sku))
            continue

        stock_on_hand = float(stock_on_hand or 0)
        variance = float(counted_qty) - stock_on_hand

        if variance == 0:
            continue

        product = products_by_sku[sku]
        note_text = str(notes) if notes else "Stock take adjustment"

        movement = StockMovement(
            tenant_id=tenant_id,
            product_id=product.id,
            quantity=variance,
            reason="stock_take",
            reference_type=note_text,
        )
        session.add(movement)
        await session.flush()
        movement_ids.append(str(movement.id))
        adjusted += 1

    await session.commit()

    return {
        "processed": processed,
        "adjusted": adjusted,
        "skipped": skipped,
        "movements_created": movement_ids,
    }


@router.post("/customers", response_model=schemas.CustomerResponse)
async def create_customer(
    data: schemas.CustomerCreate,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
    limits: LimitEnforcer = Depends(get_limit_enforcer),
):
    await limits.check_customer_limit()
    return await service.create_customer(session, tenant_id, data)

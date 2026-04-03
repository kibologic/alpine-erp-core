from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List
import uuid
from datetime import datetime, timezone

from core.db import get_session
from core.auth import get_current_tenant
from core.auth_deps import get_current_user
from core.models import Tab, TabLine, Product, TerminalConfig, KitchenOrder, KitchenOrderLine

router = APIRouter(prefix="/pos/tabs", tags=["pos-tabs"])

class CreateTabBody(BaseModel):
    name: str
    session_id: str

class AddTabLineBody(BaseModel):
    product_id: str
    quantity: float = 1.0

class KitchenOrderLineSchema(BaseModel):
    product_id: str
    name: str
    quantity: float
    notes: Optional[str] = None

class CreateKitchenOrderBody(BaseModel):
    session_id: str
    tab_id: Optional[str] = None
    lines: List[KitchenOrderLineSchema]

class CloseTabBody(BaseModel):
    payment_method: str = "cash"
    amount_tendered: Optional[float] = None

def tab_to_dict(tab: Tab, lines: List[TabLine] = []) -> dict:
    return {
        "id": str(tab.id),
        "name": tab.name,
        "status": tab.status,
        "subtotal": float(tab.subtotal),
        "tax": float(tab.tax),
        "total": float(tab.total),
        "created_at": tab.created_at.isoformat() if tab.created_at else None,
        "lines": [
            {
                "id": str(l.id),
                "product_id": str(l.product_id),
                "name": l.name,
                "quantity": float(l.quantity),
                "unit_price": float(l.unit_price),
                "line_total": float(l.line_total),
                "tax": float(l.tax)
            }
            for l in lines
        ]
    }

@router.get("")
async def list_tabs(
    session_id: Optional[str] = None,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    query = select(Tab).where(
        Tab.tenant_id == current_user["tenant_id"],
        Tab.status == "open"
    )
    if session_id:
        query = query.where(
            Tab.session_id == session_id
        )
    result = await db.execute(
        query.order_by(Tab.created_at.desc())
    )
    tabs = result.scalars().all()
    return [tab_to_dict(t) for t in tabs]

@router.post("")
async def create_tab(
    body: CreateTabBody,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    tab = Tab(
        id=str(uuid.uuid4()),
        tenant_id=current_user["tenant_id"],
        session_id=body.session_id,
        name=body.name,
        status="open",
        created_by=current_user["user_id"]
    )
    db.add(tab)
    await db.commit()
    await db.refresh(tab)
    return tab_to_dict(tab)

@router.get("/{tab_id}")
async def get_tab(
    tab_id: str,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    tab_result = await db.execute(
        select(Tab).where(Tab.id == tab_id, Tab.tenant_id == current_user["tenant_id"])
    )
    tab = tab_result.scalar_one_or_none()
    if not tab:
        raise HTTPException(404, "Tab not found")
    
    lines_result = await db.execute(
        select(TabLine).where(TabLine.tab_id == tab_id)
        .order_by(TabLine.added_at)
    )
    lines = lines_result.scalars().all()
    return tab_to_dict(tab, lines)

@router.post("/{tab_id}/lines")
async def add_tab_line(
    tab_id: str,
    body: AddTabLineBody,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    tab_result = await db.execute(
        select(Tab).where(Tab.id == tab_id, Tab.tenant_id == current_user["tenant_id"])
    )
    tab = tab_result.scalar_one_or_none()
    if not tab or tab.status != "open":
        raise HTTPException(400, "Tab not found or closed")
    
    prod_result = await db.execute(
        select(Product).where(
            Product.id == body.product_id,
            Product.tenant_id == current_user["tenant_id"]
        )
    )
    product = prod_result.scalar_one_or_none()
    if not product:
        raise HTTPException(404, "Product not found")
    
    # Use product.price (backend uses Numeric(12, 2))
    price = float(product.price)
    line_total = round(price * body.quantity, 2)
    tax = round(line_total * 0.165, 2)
    
    line = TabLine(
        id=str(uuid.uuid4()),
        tab_id=tab_id,
        product_id=product.id,
        name=product.name,
        quantity=body.quantity,
        unit_price=price,
        line_total=line_total,
        tax=tax
    )
    db.add(line)
    
    # Update tab totals
    # We can just update the tab sum after adding
    await db.flush() # Ensure line is in DB for aggregate functions
    
    all_lines_result = await db.execute(
        select(TabLine).where(TabLine.tab_id == tab_id)
    )
    all_lines = all_lines_result.scalars().all()
    
    tab.subtotal = round(sum(float(l.line_total) for l in all_lines), 2)
    tab.tax = round(sum(float(l.tax) for l in all_lines), 2)
    tab.total = round(float(tab.subtotal) + float(tab.tax), 2)
    
    await db.commit()
    await db.refresh(tab)
    
    return tab_to_dict(tab, all_lines)

@router.delete("/{tab_id}/lines/{line_id}")
async def remove_tab_line(
    tab_id: str,
    line_id: str,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    line_result = await db.execute(
        select(TabLine).where(
            TabLine.id == line_id,
            TabLine.tab_id == tab_id
        )
    )
    line = line_result.scalar_one_or_none()
    if not line:
        raise HTTPException(404, "Line not found")
    
    await db.delete(line)
    
    tab_result = await db.execute(
        select(Tab).where(Tab.id == tab_id, Tab.tenant_id == current_user["tenant_id"])
    )
    tab = tab_result.scalar_one_or_none()
    
    # Explicitly flush/commit might be needed before total recalc if not using atomic updates
    await db.flush() 
    
    remaining_result = await db.execute(
        select(TabLine).where(TabLine.tab_id == tab_id)
    )
    remaining = remaining_result.scalars().all()
    
    tab.subtotal = round(sum(float(l.line_total) for l in remaining), 2)
    tab.tax = round(sum(float(l.tax) for l in remaining), 2)
    tab.total = round(float(tab.subtotal) + float(tab.tax), 2)
    
    await db.commit()
    return {"message": "Line removed"}

@router.post("/{tab_id}/close")
async def close_tab(
    tab_id: str,
    body: CloseTabBody,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    tab_result = await db.execute(
        select(Tab).where(Tab.id == tab_id, Tab.tenant_id == current_user["tenant_id"])
    )
    tab = tab_result.scalar_one_or_none()
    if not tab or tab.status != "open":
        raise HTTPException(400, "Tab not found or already closed")
    
    lines_result = await db.execute(
        select(TabLine).where(TabLine.tab_id == tab_id)
    )
    lines = lines_result.scalars().all()
    
    if not lines:
        raise HTTPException(400, "Cannot close empty tab")
    
    # Calculate totals one last time to be sure
    total = float(tab.total)
    
    # Validate cash payment
    change = 0.0
    if body.payment_method == "cash" and body.amount_tendered is not None:
        if body.amount_tendered < total:
            raise HTTPException(400, {
                "code": "INSUFFICIENT_PAYMENT",
                "message": f"Amount tendered is less than total"
            })
        change = round(max(0, body.amount_tendered - total), 2)
    
    tab.status = "closed"
    tab.closed_at = datetime.now(timezone.utc)
    await db.commit()
    
    return {
        **tab_to_dict(tab, lines),
        "change": change,
        "payment_method": body.payment_method
    }

@router.post("/kitchen-orders")
async def create_kitchen_order(
    body: CreateKitchenOrderBody,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    kitchen_order = KitchenOrder(
        id=str(uuid.uuid4()),
        tenant_id=current_user["tenant_id"],
        session_id=body.session_id,
        tab_id=body.tab_id,
        status="pending"
    )
    db.add(kitchen_order)
    
    for line in body.lines:
        ko_line = KitchenOrderLine(
            id=str(uuid.uuid4()),
            kitchen_order_id=kitchen_order.id,
            product_id=line.product_id,
            name=line.name,
            quantity=line.quantity,
            notes=line.notes
        )
        db.add(ko_line)
    
    await db.commit()
    await db.refresh(kitchen_order)
    
    # In a real scenario, we would trigger a WebSocket event here
    return {"message": "Order sent to kitchen", "order_id": kitchen_order.id}

@router.get("/config/{terminal_id}")
async def get_terminal_config(
    terminal_id: str,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user)
):
    result = await db.execute(
        select(TerminalConfig).where(
            TerminalConfig.tenant_id == current_user["tenant_id"],
            TerminalConfig.terminal_id == terminal_id
        )
    )
    config = result.scalar_one_or_none()
    
    if not config:
        # Return default instant-only config
        return {
            "terminal_id": terminal_id,
            "name": "Terminal",
            "enabled_modes": ["instant"],
            "default_mode": "instant",
            "config": {}
        }
    
    return {
        "terminal_id": config.terminal_id,
        "name": config.name,
        "enabled_modes": config.enabled_modes,
        "default_mode": config.default_mode,
        "config": config.config
    }

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.auth import get_current_tenant
from core.limits import LimitEnforcer, get_limit_enforcer
from core.models import Sale
from . import schemas, service

router = APIRouter(prefix="/pos", tags=["POS"])


@router.get("/sessions")
async def list_sessions(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    from core.models import CashSession
    from sqlalchemy import select

    result = await session.execute(
        select(CashSession)
        .where(CashSession.tenant_id == tenant_id)
        .order_by(CashSession.opened_at.desc())
        .limit(50)
    )
    sessions = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "register_id": s.register_id,
            "status": s.status,
            "opening_float": float(s.opening_float),
            "closing_amount": float(s.closing_amount) if s.closing_amount else None,
            "discrepancy": float(s.discrepancy) if s.discrepancy else None,
            "opened_at": s.opened_at.isoformat(),
            "closed_at": s.closed_at.isoformat() if s.closed_at else None,
        }
        for s in sessions
    ]


@router.post("/sessions/open", response_model=schemas.SessionResponse)
async def open_session(
    data: schemas.SessionOpen,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    # In a real app, we'd get user_id from auth token
    user_id = "00000000-0000-0000-0000-000000000002" # admin@kibologic.com
    try:
        return await service.open_session(session, tenant_id, user_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/close/{session_id}", response_model=schemas.SessionResponse)
async def close_session(
    session_id: str,
    data: schemas.SessionClose,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    user_id = "00000000-0000-0000-0000-000000000002" # admin@kibologic.com
    try:
        return await service.close_session(session, tenant_id, user_id, session_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sessions/current/{register_id}", response_model=Optional[schemas.SessionResponse])
async def get_current_session(
    register_id: str,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    return await service.get_current_session(session, tenant_id, register_id)


@router.get("/sales")
async def list_sales(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    result = await session.execute(
        select(Sale)
        .where(Sale.tenant_id == tenant_id)
        .order_by(Sale.created_at.desc())
        .limit(100)
    )
    sales = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "sale_number": s.sale_number,
            "subtotal": float(s.subtotal),
            "tax": float(s.tax),
            "discount": float(s.discount),
            "total": float(s.total),
            "status": s.status,
            "created_at": s.created_at.isoformat(),
        }
        for s in sales
    ]


@router.post("/sales", response_model=schemas.SaleResponse)
async def create_sale(
    data: schemas.SaleCreate,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
    limits: LimitEnforcer = Depends(get_limit_enforcer),
):
    user_id = "00000000-0000-0000-0000-000000000002" # admin@kibologic.com
    await limits.check_sales_limit()
    try:
        return await service.create_sale(session, tenant_id, user_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sales/{sale_id}/refund", response_model=schemas.SaleResponse)
async def refund_sale(
    sale_id: str,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    user_id = "00000000-0000-0000-0000-000000000002" # admin@kibologic.com
    try:
        return await service.refund_sale(session, tenant_id, user_id, sale_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sales/{sale_id}", response_model=schemas.SaleResponse)
async def get_sale(
    sale_id: str,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    # Basic lookup
    from core.models import Sale
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    
    result = await session.execute(
        select(Sale)
        .where(Sale.id == sale_id, Sale.tenant_id == tenant_id)
        .options(selectinload(Sale.lines), selectinload(Sale.payments))
    )
    sale = result.scalar_one_or_none()
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    return sale

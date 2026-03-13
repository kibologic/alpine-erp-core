from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.auth import get_current_tenant
from core.limits import LimitEnforcer, get_limit_enforcer
from . import schemas, service

router = APIRouter(prefix="/pos", tags=["POS"])


@router.post("/sessions/open", response_model=schemas.SessionResponse)
async def open_session(
    data: schemas.SessionOpen,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    # In a real app, we'd get user_id from auth token
    user_id = "00000000-0000-0000-0000-000000000000" # Placeholder
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
    user_id = "00000000-0000-0000-0000-000000000000" # Placeholder
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


@router.post("/sales", response_model=schemas.SaleResponse)
async def create_sale(
    data: schemas.SaleCreate,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
    limits: LimitEnforcer = Depends(get_limit_enforcer),
):
    user_id = "00000000-0000-0000-0000-000000000000" # Placeholder
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
    user_id = "00000000-0000-0000-0000-000000000000" # Placeholder
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

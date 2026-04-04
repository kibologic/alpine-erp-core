from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from gbil.math import Order, Cash, Money

from core.db import get_session
from core.auth import get_current_tenant
from core.auth_deps import get_current_user
from core.limits import LimitEnforcer, get_limit_enforcer
from core.models import Tenant, Sale, Product, CashSession, FiscalSubmission, TerminalConfig
from core.fiscal import get_fiscal_service_for_tenant, build_fiscal_sale
from core.ws_manager import manager
from . import schemas, service

import json
import logging
import uuid
from sqlalchemy import select

logger = logging.getLogger("alpine.pos")

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
    current_user: dict = Depends(get_current_user),
):
    from core.limits import check_limit
    limit_res = await check_limit(tenant_id, session, "terminal", data.device_id)
    if not limit_res.get("allowed"):
        raise HTTPException(
            status_code=403, 
            detail=limit_res.get("upgrade_message", "Limit exceeded")
        )
        
    try:
        return await service.open_session(session, tenant_id, current_user["user_id"], data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sessions/close/{session_id}", response_model=schemas.SessionResponse)
async def close_session(
    session_id: str,
    data: schemas.SessionClose,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
    current_user: dict = Depends(get_current_user),
):
    try:
        return await service.close_session(session, tenant_id, current_user["user_id"], session_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/terminals")
async def list_terminals(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    result = await session.execute(
        select(TerminalConfig)
        .where(TerminalConfig.tenant_id == tenant_id)
        .order_by(TerminalConfig.created_at)
    )
    configs = result.scalars().all()
    return [
        {
            "terminal_id": c.terminal_id,
            "name": c.name,
            "enabled_modes": c.enabled_modes,
            "default_mode": c.default_mode,
        }
        for c in configs
    ]


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


@router.post("/sales")
async def create_sale(
    data: schemas.SaleCreate,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
    limits: LimitEnforcer = Depends(get_limit_enforcer),
    current_user: dict = Depends(get_current_user),
):
    await limits.check_sales_limit()

    # ── gbil-math: calculate order totals precisely ──
    order_result = Order.calculate([
        {
            "unit_price": float(line.unit_price),
            "quantity": float(line.quantity),
            "tax_rate": "0.165",
            "discount_fixed": float(line.discount) if line.discount else 0,
        }
        for line in data.lines
    ])

    # ── gbil-math: validate cash payment sufficiency ──
    change_denominations = {}
    for payment in data.payments:
        if payment.method == "cash":
            cash_result = Cash.tender(
                total=order_result.total,
                tendered=float(payment.amount)
            )
            if not cash_result.sufficient:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "INSUFFICIENT_PAYMENT",
                        "message": (
                            f"Amount tendered "
                            f"({Money.format(float(payment.amount), 'MWK')}) "
                            f"is less than total "
                            f"({Money.format(order_result.total, 'MWK')})"
                        ),
                        "total": float(order_result.total),
                        "tendered": float(payment.amount),
                        "shortfall": float(
                            float(order_result.total) - float(payment.amount)
                        )
                    }
                )
            change_denominations = Cash.suggest_denominations(
                float(cash_result.change)
            )

    try:
        sale = await service.create_sale(session, tenant_id, current_user["user_id"], data)
        # Attach change denominations to response dict
        sale_dict = {
            "id": sale.id,
            "sale_number": sale.sale_number,
            "customer_id": str(sale.customer_id) if sale.customer_id else None,
            "cashier_id": str(sale.cashier_id),
            "session_id": str(sale.session_id),
            "subtotal": float(sale.subtotal),
            "tax": float(sale.tax),
            "discount": float(sale.discount),
            "total": float(sale.total),
            "status": sale.status,
            "created_at": sale.created_at.isoformat(),
            "lines": [
                {
                    "id": str(l.id),
                    "product_id": str(l.product_id),
                    "quantity": float(l.quantity),
                    "unit_price": float(l.unit_price),
                    "line_total": float(l.line_total),
                }
                for l in sale.lines
            ],
            "payments": [
                {
                    "id": str(p.id),
                    "method": p.method,
                    "amount": float(p.amount),
                    "created_at": p.created_at.isoformat(),
                }
                for p in sale.payments
            ],
            "change_denominations": change_denominations,
        }

        # ── gbil-fiscal: automatic submission ──
        fiscal_data = {}
        try:
            # Fetch tenant details for fiscal routing
            tenant_result = await session.execute(
                select(Tenant).where(Tenant.id == current_user["tenant_id"])
            )
            tenant = tenant_result.scalar_one_or_none()

            fiscal_service = await get_fiscal_service_for_tenant(
                tenant_id=str(current_user["tenant_id"]),
                country=tenant.country or "default",
                fiscal_provider=tenant.fiscal_provider,
                fiscal_config=tenant.fiscal_config or {}
            )
            
            # Populate fiscal lines with product classification
            fiscal_lines = []
            for line in data.lines:
                prod_result = await session.execute(
                    select(Product).where(Product.id == line.product_id)
                )
                product = prod_result.scalar_one_or_none()
                fiscal_lines.append({
                    "product_id": str(line.product_id),
                    "name": product.name if product else "Product",
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "tax": line.tax,
                    "line_total": line.line_total,
                    "unspsc_code": product.unspsc_code if product else None
                })
            
            # Load session to get register_id for fiscal report
            session_result = await session.execute(
                select(CashSession).where(CashSession.id == data.session_id)
            )
            cash_session = session_result.scalar_one_or_none()
            terminal_id = cash_session.register_id if cash_session else "REG-001"

            # Map Alpine sale to Fiscal contract
            fiscal_sale = build_fiscal_sale(
                sale_id=str(sale.id),
                tenant_id=str(tenant_id),
                terminal_id=terminal_id,
                cashier_id=str(current_user["user_id"]),
                lines=fiscal_lines,
                payments=[{"method": p.method, "amount": float(p.amount)} for p in data.payments],
                subtotal=float(sale.subtotal),
                tax=float(sale.tax),
                total=float(sale.total),
                receipt_counter=int(sale.sale_number.split("-")[-1]) if "-" in sale.sale_number else 1
            )

            fiscal_result, fiscal_block = await fiscal_service.submit_sale(fiscal_sale)

            # Record submission in DB
            fiscal_sub = FiscalSubmission(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                sale_id=sale.id,
                provider=fiscal_service._adapter.provider_name,
                fiscal_code=fiscal_result.fiscal_code,
                qr_code=fiscal_result.qr_code,
                receipt_block=json.dumps(fiscal_block.to_dict()),
                status="submitted" if fiscal_result.success else "queued",
                submitted_at=fiscal_result.timestamp,
                offline=fiscal_result.offline,
                error_message=fiscal_result.error
            )
            session.add(fiscal_sub)
            await session.commit()

            fiscal_data = {
                "fiscal_code": fiscal_result.fiscal_code,
                "receipt_block": fiscal_block.to_dict(),
                "status": "submitted" if fiscal_result.success else "queued",
                "offline": fiscal_result.offline
            }
        except Exception as fe:
            logger.warning(f"Fiscal submission failed for sale {sale.id}: {fe}")
            fiscal_data = {
                "fiscal_code": None,
                "receipt_block": {
                    "type": "fiscal_pending",
                    "lines": ["FISCAL CODE: PENDING"]
                },
                "status": "queued",
                "offline": True
            }

        # ── Real-time Notification ──
        try:
            await manager.broadcast(
                tenant_id,
                "pos.sale.created",
                {
                    "sale_id": str(sale.id),
                    "total": float(sale.total),
                    "fiscal_code": fiscal_data.get("fiscal_code"),
                    "cashier_id": str(current_user["user_id"])
                }
            )
        except Exception as we:
            logger.warning(f"WebSocket broadcast failed: {we}")

        # Merge fiscal results into response
        sale_dict["fiscal"] = fiscal_data
        return sale_dict

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sale creation error: {e}")
        await session.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sales/{sale_id}/refund", response_model=schemas.SaleResponse)
async def refund_sale(
    sale_id: str,
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
    current_user: dict = Depends(get_current_user),
):
    try:
        return await service.refund_sale(session, tenant_id, current_user["user_id"], sale_id)
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

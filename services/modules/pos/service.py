from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Sequence
import uuid

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from core.models import CashSession, Sale, SaleLine, Payment, StockMovement, User
from core.audit import log_event
from core.events import publish_event
from core.ws_manager import manager
from . import schemas


async def get_current_session(session: AsyncSession, tenant_id: str, register_id: str) -> Optional[CashSession]:
    result = await session.execute(
        select(CashSession).where(
            CashSession.tenant_id == tenant_id,
            CashSession.register_id == register_id,
            CashSession.status == "open"
        )
    )
    return result.scalar_one_or_none()


async def open_session(
    session: AsyncSession, 
    tenant_id: str, 
    user_id: str, 
    data: schemas.SessionOpen
) -> CashSession:
    # Check if a session is already open for this register
    existing = await get_current_session(session, tenant_id, data.register_id)
    if existing:
        raise ValueError(f"Session already open for register {data.register_id}")

    new_session = CashSession(
        tenant_id=tenant_id,
        register_id=data.register_id,
        opened_by=user_id,
        opening_float=data.opening_float,
        status="open",
        opened_at=datetime.utcnow()
    )
    session.add(new_session)
    await session.commit()
    await session.refresh(new_session)
    
    # Audit log
    await log_event(session, tenant_id, user_id, "OPEN_SESSION", "CashSession", str(new_session.id), {"register_id": data.register_id})
    await manager.broadcast(
        tenant_id=str(tenant_id),
        event_type="pos.session.opened",
        payload={
            "session_id": str(new_session.id),
            "register_id": new_session.register_id,
            "opened_by": str(new_session.opened_by) if new_session.opened_by else None,
            "opening_float": float(new_session.opening_float)
        }
    )

    return new_session


async def close_session(
    session: AsyncSession, 
    tenant_id: str, 
    user_id: str, 
    session_id: str,
    data: schemas.SessionClose
) -> CashSession:
    result = await session.execute(
        select(CashSession).where(CashSession.id == session_id, CashSession.tenant_id == tenant_id)
    )
    pos_session = result.scalar_one_or_none()
    if not pos_session or pos_session.status != "open":
        raise ValueError("Active session not found")

    # Calculate expected amount (opening_float + cash payments)
    payments_result = await session.execute(
        select(func.sum(Payment.amount)).join(Sale).where(
            Sale.session_id == session_id,
            Payment.method == "cash"
        )
    )
    cash_payments_total = payments_result.scalar() or Decimal("0")
    expected = pos_session.opening_float + cash_payments_total
    
    pos_session.status = "closed"
    pos_session.closed_by = user_id
    pos_session.closed_at = datetime.utcnow()
    pos_session.closing_amount = data.closing_amount
    pos_session.discrepancy = data.closing_amount - expected
    
    await session.commit()
    await session.refresh(pos_session)
    
    # Audit log
    await log_event(session, tenant_id, user_id, "CLOSE_SESSION", "CashSession", str(pos_session.id), {"discrepancy": str(pos_session.discrepancy)})
    await manager.broadcast(
        tenant_id=str(tenant_id),
        event_type="pos.session.closed",
        payload={
            "session_id": str(session_id),
            "register_id": pos_session.register_id,
            "closing_amount": float(pos_session.closing_amount),
            "discrepancy": float(pos_session.discrepancy)
        }
    )

    return pos_session


async def create_sale(
    session: AsyncSession, 
    tenant_id: str, 
    user_id: str, 
    data: schemas.SaleCreate
) -> Sale:
    # Ensure session is open
    result = await session.execute(
        select(CashSession).where(CashSession.id == data.session_id, CashSession.tenant_id == tenant_id)
    )
    pos_session = result.scalar_one_or_none()
    if not pos_session or pos_session.status != "open":
        raise ValueError("Session is not open")

    # Atomic transaction
    async with session.begin_nested():
        # 1. Generate sale number
        count_result = await session.execute(select(func.count(Sale.id)).where(Sale.tenant_id == tenant_id))
        count = count_result.scalar() or 0
        sale_number = f"SAL-{datetime.utcnow().strftime('%Y%m%d')}-{count + 1:04d}"

        # 2. Create Sale header
        sale = Sale(
            tenant_id=tenant_id,
            sale_number=sale_number,
            customer_id=data.customer_id,
            cashier_id=user_id,
            session_id=data.session_id,
            subtotal=data.subtotal,
            tax=data.tax,
            discount=data.discount,
            total=data.total,
            status="completed"
        )
        session.add(sale)
        await session.flush() # Get sale.id

        # 3. Create Sale Lines and Stock Movements
        for line_data in data.lines:
            line = SaleLine(
                tenant_id=tenant_id,
                sale_id=sale.id,
                product_id=line_data.product_id,
                quantity=line_data.quantity,
                unit_price=line_data.unit_price,
                discount=line_data.discount,
                tax=line_data.tax,
                line_total=line_data.line_total
            )
            session.add(line)
            
            # Stock Movement (Negative for sale)
            movement = StockMovement(
                tenant_id=tenant_id,
                product_id=line_data.product_id,
                quantity=-line_data.quantity,
                reason="Sale",
                reference_type="Sale",
                reference_id=sale.id,
                created_by=user_id
            )
            session.add(movement)

        # 4. Create Payments
        for pay_data in data.payments:
            payment = Payment(
                tenant_id=tenant_id,
                sale_id=sale.id,
                method=pay_data.method,
                amount=pay_data.amount
            )
            session.add(payment)

    await session.commit()
    await session.refresh(sale)
    
    # Audit log
    await log_event(session, tenant_id, user_id, "CREATE_SALE", "Sale", str(sale.id), {"sale_number": sale.sale_number, "total": str(sale.total)})
    await manager.broadcast(
        tenant_id=str(tenant_id),
        event_type="pos.sale.created",
        payload={
            "sale_id": str(sale.id),
            "sale_number": str(sale.sale_number),
            "total": float(sale.total),
            "cashier_id": str(sale.cashier_id) if sale.cashier_id else None,
            "session_id": str(sale.session_id),
            "items_count": len(data.lines)
        }
    )
    
    # We need to load lines and payments for the response
    result = await session.execute(
        select(Sale).where(Sale.id == sale.id).options(
            selectinload(Sale.lines), selectinload(Sale.payments)
        )
    )
    return result.scalar_one()


async def refund_sale(
    session: AsyncSession, 
    tenant_id: str, 
    user_id: str, 
    sale_id: str
) -> Sale:
    result = await session.execute(
        select(Sale).where(Sale.id == sale_id, Sale.tenant_id == tenant_id).options(selectinload(Sale.lines))
    )
    sale = result.scalar_one_or_none()
    if not sale or sale.status == "refunded":
        raise ValueError("Sale not found or already refunded")

    async with session.begin_nested():
        sale.status = "refunded"
        
        # Reverse all stock movements
        for line in sale.lines:
            movement = StockMovement(
                tenant_id=tenant_id,
                product_id=line.product_id,
                quantity=line.quantity, # Positive to return stock
                reason="Refund",
                reference_type="Refund",
                reference_id=sale.id,
                created_by=user_id
            )
            session.add(movement)

    await session.commit()
    await session.refresh(sale)
    
    # Audit log
    await log_event(session, tenant_id, user_id, "REFUND_SALE", "Sale", str(sale.id), {"sale_number": sale.sale_number})
    await publish_event("pos.sale.refunded", {"sale_id": str(sale.id), "sale_number": sale.sale_number}, tenant_id=tenant_id)

    return sale

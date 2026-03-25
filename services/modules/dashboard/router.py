from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _require_tenant(x_tenant_id: str | None = Header(default=None)) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")
    return x_tenant_id


@router.get("/pulse")
async def get_pulse(
    tenant_id: str = Depends(_require_tenant),
    db: AsyncSession = Depends(get_session),
):
    from sqlalchemy import text

    today = date.today().isoformat()
    revenue_today = 0.0
    transactions_today = 0
    low_stock_count = 0
    open_sessions_count = 0
    recent_transactions = []

    # POS transactions — best-effort, table may not exist yet
    try:
        tx_row = await db.execute(
            text("""
                SELECT
                    COALESCE(SUM(total), 0) AS revenue,
                    COUNT(*) AS tx_count
                FROM pos_transactions
                WHERE tenant_id = :tid AND DATE(created_at) = :today
            """),
            {"tid": tenant_id, "today": today},
        )
        tx_row = tx_row.mappings().first()
        revenue_today = float(tx_row["revenue"] or 0)
        transactions_today = int(tx_row["tx_count"] or 0)
    except Exception:
        pass

    try:
        recent_row = await db.execute(
            text("""
                SELECT id, total, created_at
                FROM pos_transactions
                WHERE tenant_id = :tid
                ORDER BY created_at DESC
                LIMIT 5
            """),
            {"tid": tenant_id},
        )
        recent_transactions = [
            {
                "id": str(r["id"]),
                "total": float(r["total"]),
                "created_at": r["created_at"].isoformat() + "Z",
            }
            for r in recent_row.mappings().all()
        ]
    except Exception:
        pass

    # Low stock
    try:
        ls_row = await db.execute(
            text("""
                SELECT COUNT(*) AS cnt FROM products
                WHERE tenant_id = :tid AND stock_level < reorder_point
            """),
            {"tid": tenant_id},
        )
        low_stock_count = int(ls_row.scalar() or 0)
    except Exception:
        pass

    # Open POS sessions
    try:
        os_row = await db.execute(
            text("SELECT COUNT(*) AS cnt FROM pos_sessions WHERE tenant_id = :tid AND status = 'open'"),
            {"tid": tenant_id},
        )
        open_sessions_count = int(os_row.scalar() or 0)
    except Exception:
        pass

    avg_basket = round(revenue_today / transactions_today, 2) if transactions_today > 0 else 0.0

    return {
        "date": today,
        "revenue_today": round(revenue_today, 2),
        "transactions_today": transactions_today,
        "avg_basket": avg_basket,
        "currency": "USD",
        "alerts": {
            "low_stock_count": low_stock_count,
            "open_sessions_count": open_sessions_count,
        },
        "recent_transactions": recent_transactions,
    }

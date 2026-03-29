import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session

_JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("JWT_SECRET"))
_JWT_ALGORITHM = "HS256"

router = APIRouter(prefix="/inventory/stock-take", tags=["stock-take"])


def _require_tenant(x_tenant_id: str | None = Header(default=None)) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")
    return x_tenant_id


# ── Models ───────────────────────────────────────────────────────────────────

class CountBody(BaseModel):
    product_id: str
    counted_qty: float
    device_id: str
    reason: str | None = None
    photo_url: str | None = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/active")
async def get_active_session(
    tenant_id: str = Depends(_require_tenant),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import text

    row = await session.execute(
        text("""
            SELECT s.id, s.location, s.created_by, s.started_at, s.status,
                   COUNT(c.id) AS item_count
            FROM stock_take_sessions s
            LEFT JOIN stock_take_counts c ON c.session_id = s.id
            WHERE s.tenant_id = :tenant_id AND s.status = 'active'
            GROUP BY s.id
            ORDER BY s.started_at DESC
            LIMIT 1
        """),
        {"tenant_id": tenant_id},
    )
    row = row.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="no_active_session")

    return {
        "id": str(row["id"]),
        "location": row["location"],
        "created_by": str(row["created_by"]),
        "started_at": row["started_at"].isoformat() + "Z",
        "status": row["status"],
        "item_count": row["item_count"],
    }


@router.post("/{session_id}/count")
async def submit_count(
    session_id: str,
    body: CountBody,
    tenant_id: str = Depends(_require_tenant),
    db: AsyncSession = Depends(get_session),
):
    from sqlalchemy import text

    # Verify session belongs to tenant
    sess_row = await db.execute(
        text("SELECT id FROM stock_take_sessions WHERE id = :id AND tenant_id = :tid AND status = 'active'"),
        {"id": session_id, "tid": tenant_id},
    )
    if not sess_row.first():
        raise HTTPException(status_code=404, detail="session_not_found")

    # Get system_qty from products table (best-effort — table may not exist yet)
    system_qty = 0.0
    try:
        qty_row = await db.execute(
            text("SELECT stock_level FROM products WHERE id = :pid AND tenant_id = :tid"),
            {"pid": body.product_id, "tid": tenant_id},
        )
        qty_row = qty_row.first()
        if qty_row:
            system_qty = float(qty_row[0] or 0)
    except Exception:
        pass

    variance = body.counted_qty - system_qty
    count_id = str(uuid.uuid4())

    # Check for duplicate product on same session from different device
    dup = await db.execute(
        text("""
            SELECT id, device_id FROM stock_take_counts
            WHERE session_id = :sid AND product_id = :pid AND tenant_id = :tid
        """),
        {"sid": session_id, "pid": body.product_id, "tid": tenant_id},
    )
    existing = dup.mappings().all()
    flagged = len(existing) > 0 and any(r["device_id"] != body.device_id for r in existing)

    if flagged:
        await db.execute(
            text("UPDATE stock_take_counts SET flagged = true WHERE session_id = :sid AND product_id = :pid AND tenant_id = :tid"),
            {"sid": session_id, "pid": body.product_id, "tid": tenant_id},
        )

    await db.execute(
        text("""
            INSERT INTO stock_take_counts
              (id, session_id, tenant_id, product_id, device_id, counted_by,
               system_qty, counted_qty, reason, photo_url, flagged)
            VALUES
              (:id, :session_id, :tenant_id, :product_id, :device_id, :counted_by,
               :system_qty, :counted_qty, :reason, :photo_url, :flagged)
        """),
        {
            "id": count_id,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "product_id": body.product_id,
            "device_id": body.device_id,
            "counted_by": tenant_id,  # placeholder until JWT threading is added
            "system_qty": system_qty,
            "counted_qty": body.counted_qty,
            "reason": body.reason,
            "photo_url": body.photo_url,
            "flagged": flagged,
        },
    )
    await db.commit()

    return {"id": count_id, "variance": variance, "flagged": flagged}


@router.get("/{session_id}/progress")
async def get_progress(
    session_id: str,
    tenant_id: str = Depends(_require_tenant),
    db: AsyncSession = Depends(get_session),
):
    from sqlalchemy import text

    sess_row = await db.execute(
        text("SELECT id FROM stock_take_sessions WHERE id = :id AND tenant_id = :tid"),
        {"id": session_id, "tid": tenant_id},
    )
    if not sess_row.first():
        raise HTTPException(status_code=404, detail="session_not_found")

    stats = await db.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE synced_at IS NOT NULL) AS synced,
                COUNT(*) FILTER (WHERE synced_at IS NULL) AS pending
            FROM stock_take_counts
            WHERE session_id = :sid AND tenant_id = :tid
        """),
        {"sid": session_id, "tid": tenant_id},
    )
    row = stats.mappings().first()

    # total_products: count distinct products in tenant (best-effort)
    total_products = 0
    try:
        prod_count = await db.execute(
            text("SELECT COUNT(*) FROM products WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
        total_products = prod_count.scalar() or 0
    except Exception:
        pass

    return {
        "session_id": session_id,
        "total_products": total_products,
        "counted": row["total"],
        "synced": row["synced"],
        "pending": row["pending"],
    }

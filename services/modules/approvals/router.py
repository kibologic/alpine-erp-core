import os
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session

_JWT_SECRET = os.getenv("JWT_SECRET", os.getenv("JWT_SECRET"))
_JWT_ALGORITHM = "HS256"

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _require_tenant(x_tenant_id: str | None = Header(default=None)) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")
    return x_tenant_id


class DecisionBody(BaseModel):
    decision: str  # 'approved' | 'rejected'
    note: str | None = None


def _fmt_approval(row) -> dict:
    return {
        "id": str(row["id"]),
        "entity": row["entity"],
        "entity_id": str(row["entity_id"]),
        "requested_by": str(row["requested_by"]),
        "status": row["status"],
        "requested_at": row["requested_at"].isoformat() + "Z",
        "decision_by": str(row["decision_by"]) if row["decision_by"] else None,
        "decision_note": row["decision_note"],
        "decided_at": (row["decided_at"].isoformat() + "Z") if row["decided_at"] else None,
    }


@router.get("")
async def list_approvals(
    status: str = Query(default="all"),
    tenant_id: str = Depends(_require_tenant),
    db: AsyncSession = Depends(get_session),
):
    from sqlalchemy import text

    if status == "all":
        rows = await db.execute(
            text("SELECT * FROM approvals WHERE tenant_id = :tid ORDER BY requested_at DESC"),
            {"tid": tenant_id},
        )
    else:
        rows = await db.execute(
            text("SELECT * FROM approvals WHERE tenant_id = :tid AND status = :status ORDER BY requested_at DESC"),
            {"tid": tenant_id, "status": status},
        )

    items = [_fmt_approval(r) for r in rows.mappings().all()]
    return {"items": items, "total": len(items)}


@router.get("/{approval_id}")
async def get_approval(
    approval_id: str,
    tenant_id: str = Depends(_require_tenant),
    db: AsyncSession = Depends(get_session),
):
    from sqlalchemy import text

    row = await db.execute(
        text("SELECT * FROM approvals WHERE id = :id AND tenant_id = :tid"),
        {"id": approval_id, "tid": tenant_id},
    )
    row = row.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="approval_not_found")
    return _fmt_approval(row)


@router.post("/{approval_id}/decision")
async def submit_decision(
    approval_id: str,
    body: DecisionBody,
    tenant_id: str = Depends(_require_tenant),
    db: AsyncSession = Depends(get_session),
    authorization: str | None = Header(default=None),
):
    from sqlalchemy import text

    if body.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="decision must be 'approved' or 'rejected'")

    # Extract decision_by from JWT
    decision_by = None
    if authorization and authorization.startswith("Bearer "):
        try:
            payload = jwt.decode(authorization.removeprefix("Bearer "), _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
            decision_by = payload.get("user_id")
        except JWTError:
            pass

    row = await db.execute(
        text("SELECT id, status FROM approvals WHERE id = :id AND tenant_id = :tid"),
        {"id": approval_id, "tid": tenant_id},
    )
    if not row.first():
        raise HTTPException(status_code=404, detail="approval_not_found")

    decided_at = datetime.utcnow()
    await db.execute(
        text("""
            UPDATE approvals
            SET status = :status, decision_by = :decision_by,
                decision_note = :note, decided_at = :decided_at
            WHERE id = :id AND tenant_id = :tid
        """),
        {
            "status": body.decision,
            "decision_by": decision_by,
            "note": body.note,
            "decided_at": decided_at,
            "id": approval_id,
            "tid": tenant_id,
        },
    )
    await db.commit()

    return {
        "id": approval_id,
        "status": body.decision,
        "decided_at": decided_at.isoformat() + "Z",
    }

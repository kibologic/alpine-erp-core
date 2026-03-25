import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session

router = APIRouter(prefix="/push", tags=["push"])


def _require_tenant(x_tenant_id: str | None = Header(default=None)) -> str:
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header required")
    return x_tenant_id


class PushRegisterBody(BaseModel):
    token: str
    device_id: str
    platform: str  # 'android' | 'ios'
    user_id: str


@router.post("/register")
async def register_push_token(
    body: PushRegisterBody,
    tenant_id: str = Depends(_require_tenant),
    db: AsyncSession = Depends(get_session),
):
    from sqlalchemy import text

    if body.platform not in ("android", "ios"):
        raise HTTPException(status_code=400, detail="platform must be 'android' or 'ios'")

    now = datetime.utcnow()

    # Upsert on (tenant_id, device_id)
    existing = await db.execute(
        text("SELECT id FROM push_tokens WHERE tenant_id = :tid AND device_id = :did"),
        {"tid": tenant_id, "did": body.device_id},
    )
    existing = existing.first()

    if existing:
        await db.execute(
            text("""
                UPDATE push_tokens
                SET token = :token, last_seen = :now, active = true
                WHERE tenant_id = :tid AND device_id = :did
            """),
            {"token": body.token, "now": now, "tid": tenant_id, "did": body.device_id},
        )
    else:
        await db.execute(
            text("""
                INSERT INTO push_tokens (id, tenant_id, user_id, device_id, token, platform, last_seen)
                VALUES (:id, :tid, :uid, :did, :token, :platform, :now)
            """),
            {
                "id": str(uuid.uuid4()),
                "tid": tenant_id,
                "uid": body.user_id,
                "did": body.device_id,
                "token": body.token,
                "platform": body.platform,
                "now": now,
            },
        )

    await db.commit()
    return {"registered": True}

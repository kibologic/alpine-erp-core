from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.auth import get_current_tenant
from core.models import AuditLog

router = APIRouter(prefix="/audit-log", tags=["Audit"])


@router.get("")
async def list_audit_log(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .order_by(AuditLog.timestamp.desc())
        .limit(200)
    )
    logs = result.scalars().all()
    return [
        {
            "id": str(l.id),
            "user_id": str(l.user_id) if l.user_id else None,
            "action": l.action,
            "entity": l.entity,
            "entity_id": l.entity_id,
            "detail": l.detail,
            "timestamp": l.timestamp.isoformat(),
        }
        for l in logs
    ]

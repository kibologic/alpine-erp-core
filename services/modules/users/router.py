from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import get_session
from core.auth import get_current_tenant
from core.models import User

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("")
async def list_users(
    session: AsyncSession = Depends(get_session),
    tenant_id: str = Depends(get_current_tenant),
):
    result = await session.execute(
        select(User)
        .where(User.tenant_id == tenant_id)
        .order_by(User.created_at.desc())
    )
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "role": u.role,
            "active": u.active,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]
